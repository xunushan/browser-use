"""Chrome Agent Daemon implementation."""

import asyncio
import contextlib
import json
import logging
import os
import signal
import struct
import uuid

from ..utils.jsonrpc import (
    JsonRpcError,
    create_error_response,
    create_response,
    parse_message,
)
from ..utils.paths import get_pid_path, get_socket_path

logger = logging.getLogger(__name__)


class ChromeAgentDaemon:
    """Chrome Agent Daemon - manages browser connections and tasks."""

    def __init__(self):
        self.socket_path = get_socket_path()
        self.server: asyncio.Server | None = None
        self.running = False
        self._shutdown_event = asyncio.Event()
        # Extension session management: session_id -> {writer, client_id, info}
        self._extension_sessions: dict[str, dict] = {}
        # Pending requests from CLI: request_id -> {future, writer}
        self._pending_requests: dict[str, dict] = {}
        # Lock for thread-safe access
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the daemon."""
        logger.info("Starting Chrome Agent Daemon...")

        # Remove old socket if it exists
        if self.socket_path.exists():
            self.socket_path.unlink()

        # Create Unix socket server
        self.server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
        )

        # Set socket permissions
        self.socket_path.chmod(0o600)

        # Write PID file
        pid_path = get_pid_path()
        pid_path.write_text(str(os.getpid()))

        self.running = True
        logger.info(f"Daemon listening on {self.socket_path}")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """Stop the daemon."""
        logger.info("Stopping Chrome Agent Daemon...")
        self.running = False
        self._shutdown_event.set()

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # Clean up PID file
        pid_path = get_pid_path()
        if pid_path.exists():
            pid_path.unlink()

        logger.info("Daemon stopped")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a client connection."""
        client_id = f"client-{id(writer)}"
        try:
            while self.running:
                # Read message length (4 bytes, little-endian)
                try:
                    length_bytes = await reader.readexactly(4)
                except asyncio.IncompleteReadError:
                    break

                message_length = struct.unpack("<I", length_bytes)[0]

                # Read message data
                try:
                    data = await reader.readexactly(message_length)
                except asyncio.IncompleteReadError:
                    logger.warning("Incomplete message received from %s", client_id)
                    break

                # Process message
                response = await self._process_message(data, client_id, writer)

                # Send response
                if response:
                    response_bytes = json.dumps(response).encode("utf-8")
                    writer.write(struct.pack("<I", len(response_bytes)))
                    writer.write(response_bytes)
                    await writer.drain()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            async with self._lock:
                disconnected = [
                    session_id
                    for session_id, session in self._extension_sessions.items()
                    if session.get("writer") is writer
                ]
                for session_id in disconnected:
                    del self._extension_sessions[session_id]
                    logger.info("Extension disconnected: %s", session_id)
                # A request forwarded to a writer that just went away will never
                # be answered — an extension reloading itself is the ordinary way
                # that happens. Fail it here instead of letting the caller sit
                # out the whole forwarding timeout.
                orphaned = [
                    request_id
                    for request_id, pending in self._pending_requests.items()
                    if pending["writer"] is writer
                ]
                for request_id in orphaned:
                    pending = self._pending_requests.pop(request_id)
                    if not pending["future"].done():
                        pending["future"].set_exception(
                            ConnectionError("Extension disconnected")
                        )
            writer.close()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await writer.wait_closed()

    async def _process_message(
        self, data: bytes, client_id: str = None, writer=None
    ) -> dict | None:
        """Process a JSON-RPC message."""
        try:
            message = parse_message(data)
            method = message.get("method")
            params = message.get("params", {})
            request_id = message.get("id")

            logger.debug(f"Received method: {method}, id: {request_id}")

            # Check if this is a response to a forwarded request
            if "result" in message or "error" in message:
                # This is a response from the extension
                await self._handle_extension_response(message)
                return None

            # Route to handler
            handler = self._get_handler(method)
            if handler:
                result = await handler(params, client_id, writer)
                return create_response(result, request_id)
            else:
                return create_error_response(
                    -32601,  # METHOD_NOT_FOUND
                    f"Method not found: {method}",
                    request_id,
                )

        except JsonRpcError as e:
            return create_error_response(e.code, e.message, None, e.data)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return create_error_response(
                -32603,  # INTERNAL_ERROR
                f"Internal error: {e}",
                None,
            )

    async def _handle_extension_response(self, message: dict) -> None:
        """Handle a response from the extension to a forwarded request."""
        request_id = message.get("id")
        if request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)["future"]
            if not future.done():
                if "result" in message:
                    future.set_result(message["result"])
                elif "error" in message:
                    future.set_exception(
                        RuntimeError(message["error"].get("message", "Unknown error"))
                    )
                else:
                    future.set_result(message)

    def _get_handler(self, method: str):
        """Get handler for a method."""
        handlers = {
            "system.ping": self._handle_ping,
            "system.version": self._handle_version,
            "system.ready": self._handle_ready,
            "system.stop": self._handle_stop,
            "session.register": self._handle_session_register,
            "session.unregister": self._handle_session_unregister,
            "extension.status": self._handle_extension_status,
            "extension.reload": self._handle_extension_reload,
            "tabs.list": self._handle_tabs_list,
            "tabs.open": self._handle_tabs_open,
            "tabs.navigate": self._handle_tabs_navigate,
            "tabs.claim": self._handle_tabs_claim,
            "tabs.activate": self._handle_tabs_activate,
            "sites.list": self._handle_sites_list,
            "sites.revoke": self._handle_sites_revoke,
            "page.snapshot": self._handle_page_snapshot,
            "page.click": self._handle_page_click,
            "page.fill": self._handle_page_fill,
            "page.keypress": self._handle_page_keypress,
            "page.scroll": self._handle_page_scroll,
            "page.wait": self._handle_page_wait,
            "page.validate": self._handle_page_validate,
            "page.screenshot": self._handle_page_screenshot,
            "page.extract": self._handle_page_extract,
            "page.text": self._handle_page_text,
            "page.images": self._handle_page_images,
            "page.downloadImages": self._handle_page_download_images,
            "page.media": self._handle_page_media,
            "page.downloadMedia": self._handle_page_download_media,
        }
        return handlers.get(method)

    async def _handle_ping(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle system.ping request."""
        return {
            "pong": True,
            "protocolVersion": "1.0",
            "timestamp": asyncio.get_event_loop().time(),
        }

    async def _handle_version(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle system.version request."""
        from .. import __version__

        return {
            "version": __version__,
            "protocolVersion": "1.0",
        }

    async def _handle_ready(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle system.ready request."""
        return {
            "ready": True,
            "protocolVersion": "1.0",
            "extensions": list(self._extension_sessions.keys()),
        }

    # Session management
    async def _handle_session_register(
        self, params: dict, client_id: str = None, writer=None
    ) -> dict:
        """Handle session.register from extension."""
        session_id = params.get("extensionId", f"session-{len(self._extension_sessions)}")
        async with self._lock:
            self._extension_sessions[session_id] = {
                "extensionId": session_id,
                "protocolVersion": params.get("protocolVersion"),
                "browserVersion": params.get("browserVersion"),
                "connectedAt": asyncio.get_event_loop().time(),
                "client_id": client_id,
                "writer": writer,
            }
        logger.info(f"Extension registered: {session_id}")
        return {
            "sessionId": session_id,
            "status": "registered",
        }

    async def _handle_session_unregister(
        self, params: dict, client_id: str = None, writer=None
    ) -> dict:
        """Handle session.unregister from extension."""
        session_id = params.get("extensionId")
        async with self._lock:
            if session_id in self._extension_sessions:
                del self._extension_sessions[session_id]
                logger.info(f"Extension unregistered: {session_id}")
        return {"status": "unregistered"}

    # Extension management
    async def _handle_extension_status(
        self, params: dict, client_id: str = None, writer=None
    ) -> dict:
        """Report the connected extensions. The install state is the CLI's to answer."""
        return {
            "connected": bool(self._extension_sessions),
            "sessions": [
                {
                    "extensionId": session.get("extensionId"),
                    "protocolVersion": session.get("protocolVersion"),
                    "browserVersion": session.get("browserVersion"),
                    # On the daemon's clock, so a caller can tell a session that
                    # came back after a reload from the one that never left.
                    "connectedAt": session.get("connectedAt"),
                }
                for session in self._extension_sessions.values()
            ],
        }

    async def _handle_extension_reload(
        self, params: dict, client_id: str = None, writer=None
    ) -> dict:
        """Ask the extension to reload itself from the files on disk."""
        return await self._forward_to_extension("extension.reload", params)

    # Tabs API
    async def _handle_tabs_list(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle tabs.list - forward to extension."""
        return await self._forward_to_extension("tabs.list", params)

    async def _handle_tabs_open(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle tabs.open - forward to extension."""
        return await self._forward_to_extension("tabs.open", params)

    async def _handle_tabs_navigate(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle tabs.navigate - forward to extension."""
        return await self._forward_to_extension("tabs.navigate", params)

    async def _handle_tabs_claim(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle tabs.claim - forward to extension."""
        return await self._forward_to_extension("tabs.claim", params)

    async def _handle_tabs_activate(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Activate the target tab and focus its window."""
        return await self._forward_to_extension("tabs.activate", params)

    # Sites API
    async def _handle_sites_list(self, params: dict, client_id: str = None, writer=None) -> dict:
        """List the sites the extension currently has access to.

        Chrome holds that list and only the extension can read it, so this is a
        forward like any other — the daemon keeps no copy of its own.
        """
        return await self._forward_to_extension("sites.list", params)

    async def _handle_sites_revoke(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Drop the extension's access to one site."""
        return await self._forward_to_extension("sites.revoke", params)

    # Page API
    async def _handle_page_snapshot(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle page.snapshot - forward to extension."""
        return await self._forward_to_extension("page.snapshot", params)

    async def _handle_page_click(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle page.click - forward to extension."""
        return await self._forward_to_extension("page.click", params)

    async def _handle_page_fill(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle page.fill - forward to extension."""
        return await self._forward_to_extension("page.fill", params)

    async def _handle_page_keypress(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle page.keypress - forward to extension."""
        return await self._forward_to_extension("page.keypress", params)

    async def _handle_page_scroll(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle page.scroll - forward to extension."""
        return await self._forward_to_extension("page.scroll", params)

    async def _handle_page_wait(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle page.wait - forward to extension."""
        return await self._forward_to_extension("page.wait", params)

    async def _handle_page_validate(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle page.validate - forward to extension."""
        return await self._forward_to_extension("page.validate", params)

    async def _handle_page_screenshot(
        self, params: dict, client_id: str = None, writer=None
    ) -> dict:
        """Handle page.screenshot - forward to extension."""
        return await self._forward_to_extension("page.screenshot", params)

    async def _handle_page_extract(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle page.extract - forward to extension."""
        return await self._forward_to_extension("page.extract", params)

    async def _handle_page_text(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Extract full visible text from one referenced element."""
        return await self._forward_to_extension("page.text", params)

    async def _handle_page_images(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Discover images, optionally scrolling to trigger lazy loading."""
        return await self._forward_to_extension("page.images", params)

    async def _handle_page_download_images(
        self, params: dict, client_id: str = None, writer=None
    ) -> dict:
        """Discover and download images through the user's Chrome profile."""
        return await self._forward_to_extension("page.downloadImages", params)

    async def _handle_page_media(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Discover video and audio resources in a page or container."""
        return await self._forward_to_extension("page.media", params)

    async def _handle_page_download_media(
        self, params: dict, client_id: str = None, writer=None
    ) -> dict:
        """Download directly addressable media through Chrome."""
        return await self._forward_to_extension("page.downloadMedia", params)

    async def _handle_stop(self, params: dict, client_id: str = None, writer=None) -> dict:
        """Handle system.stop - stop the daemon."""
        logger.info("Received system.stop request, shutting down...")
        # Schedule stop so response can be sent first
        asyncio.create_task(self.stop())
        return {"status": "stopping"}

    async def _forward_to_extension(self, method: str, params: dict) -> dict:
        """Forward a request to the connected extension and wait for response."""
        if not self._extension_sessions:
            return {
                "error": "No extension connected",
                "method": method,
            }

        # Get the first connected extension
        session_id = next(iter(self._extension_sessions.keys()))
        session = self._extension_sessions[session_id]
        writer = session.get("writer")

        if not writer:
            return {
                "error": "Extension writer not available",
                "method": method,
            }

        # Generate a unique request ID for this forwarded request
        request_id = f"fwd-{uuid.uuid4().hex[:8]}"

        # Create the forwarded message
        forwarded_message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            # Create a future to wait for the response. The writer is kept so
            # that a disconnect can fail the requests that writer owed.
            future: asyncio.Future = asyncio.Future()
            self._pending_requests[request_id] = {"future": future, "writer": writer}

            # Send the forwarded message to the extension
            message_bytes = json.dumps(forwarded_message).encode("utf-8")
            writer.write(struct.pack("<I", len(message_bytes)))
            writer.write(message_bytes)
            await writer.drain()

            # Wait for the response with a timeout
            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                return {
                    "error": "Timeout waiting for extension response",
                    "method": method,
                }

        except Exception as e:
            logger.error(f"Error forwarding to extension: {e}")
            return {
                "error": f"Failed to forward to extension: {e}",
                "method": method,
            }
        finally:
            # Clean up the pending request
            if request_id in self._pending_requests:
                del self._pending_requests[request_id]


async def run_daemon() -> None:
    """Run the daemon."""
    daemon = ChromeAgentDaemon()

    # Set up signal handlers
    def signal_handler(sig, frame):
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        await daemon.start()
    except Exception as e:
        logger.error(f"Daemon error: {e}")
        raise
