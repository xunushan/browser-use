"""Chrome Agent Daemon implementation."""

import asyncio
import json
import logging
import os
import signal
import struct
import sys
from pathlib import Path
from typing import Any, Optional

from ..utils.jsonrpc import (
    JsonRpcError,
    create_error_response,
    create_response,
    parse_message,
)
from ..utils.paths import get_log_dir, get_pid_path, get_socket_path

logger = logging.getLogger(__name__)


class ChromeAgentDaemon:
    """Chrome Agent Daemon - manages browser connections and tasks."""

    def __init__(self):
        self.socket_path = get_socket_path()
        self.server: Optional[asyncio.Server] = None
        self.running = False
        self._shutdown_event = asyncio.Event()

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

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle a client connection."""
        try:
            while self.running:
                # Read message length (4 bytes, little-endian)
                length_bytes = await reader.read(4)
                if not length_bytes:
                    break

                message_length = struct.unpack("<I", length_bytes)[0]

                # Read message data
                data = await reader.read(message_length)
                if len(data) != message_length:
                    logger.warning("Incomplete message received")
                    break

                # Process message
                response = await self._process_message(data)

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
            writer.close()
            await writer.wait_closed()

    async def _process_message(self, data: bytes) -> Optional[dict]:
        """Process a JSON-RPC message."""
        try:
            message = parse_message(data)
            method = message.get("method")
            params = message.get("params", {})
            request_id = message.get("id")

            logger.debug(f"Received method: {method}, id: {request_id}")

            # Route to handler
            handler = self._get_handler(method)
            if handler:
                result = await handler(params)
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

    def _get_handler(self, method: str):
        """Get handler for a method."""
        handlers = {
            "system.ping": self._handle_ping,
            "system.version": self._handle_version,
            "system.ready": self._handle_ready,
        }
        return handlers.get(method)

    async def _handle_ping(self, params: dict) -> dict:
        """Handle system.ping request."""
        return {
            "pong": True,
            "protocolVersion": "1.0",
            "timestamp": asyncio.get_event_loop().time(),
        }

    async def _handle_version(self, params: dict) -> dict:
        """Handle system.version request."""
        from .. import __version__
        return {
            "version": __version__,
            "protocolVersion": "1.0",
        }

    async def _handle_ready(self, params: dict) -> dict:
        """Handle system.ready request."""
        return {
            "ready": True,
            "protocolVersion": "1.0",
        }


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
