"""Tests for Chrome Agent Daemon."""

import asyncio
import json
import struct
from pathlib import Path

import pytest

from chrome_agent.daemon.daemon import ChromeAgentDaemon
from chrome_agent.utils.paths import get_socket_path


class TestDaemonLifecycle:
    """Test daemon startup and shutdown."""

    @pytest.fixture
    async def daemon(self):
        """Create and start a daemon for testing."""
        daemon = ChromeAgentDaemon()
        # Use a test-specific socket path
        daemon.socket_path = get_socket_path().parent / "test-daemon.sock"

        # Start daemon in background
        task = asyncio.create_task(daemon.start())

        # Wait for daemon to be ready
        for _ in range(20):
            if daemon.running:
                break
            await asyncio.sleep(0.1)

        yield daemon

        # Cleanup
        await daemon.stop()
        await task
        if daemon.socket_path.exists():
            daemon.socket_path.unlink()

    async def _send_request(self, socket_path: Path, method: str, params: dict) -> dict:
        """Send a JSON-RPC request to the daemon using asyncio."""
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            request = {
                "jsonrpc": "2.0",
                "id": "test-1",
                "method": method,
                "params": params,
            }
            request_bytes = json.dumps(request).encode("utf-8")
            writer.write(struct.pack("<I", len(request_bytes)))
            writer.write(request_bytes)
            await writer.drain()

            # Receive response
            length_bytes = await reader.read(4)
            message_length = struct.unpack("<I", length_bytes)[0]
            data = await reader.read(message_length)

            return json.loads(data.decode("utf-8"))
        finally:
            writer.close()
            await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_daemon_starts_and_listens(self, daemon):
        """Test that daemon starts and listens on socket."""
        assert daemon.running
        assert daemon.socket_path.exists()

    @pytest.mark.asyncio
    async def test_system_ping(self, daemon):
        """Test system.ping returns pong."""
        response = await self._send_request(daemon.socket_path, "system.ping", {})

        assert "result" in response
        assert response["result"]["pong"] is True
        assert response["result"]["protocolVersion"] == "1.0"

    @pytest.mark.asyncio
    async def test_system_version(self, daemon):
        """Test system.version returns version info."""
        response = await self._send_request(daemon.socket_path, "system.version", {})

        assert "result" in response
        assert "version" in response["result"]
        assert "protocolVersion" in response["result"]

    @pytest.mark.asyncio
    async def test_system_ready(self, daemon):
        """Test system.ready returns ready status."""
        response = await self._send_request(daemon.socket_path, "system.ready", {})

        assert "result" in response
        assert response["result"]["ready"] is True

    @pytest.mark.asyncio
    async def test_unknown_method_returns_error(self, daemon):
        """Test that unknown method returns METHOD_NOT_FOUND error."""
        response = await self._send_request(daemon.socket_path, "unknown.method", {})

        assert "error" in response
        assert response["error"]["code"] == -32601  # METHOD_NOT_FOUND

    @pytest.mark.asyncio
    async def test_session_register(self, daemon):
        """Test session.register stores extension session."""
        response = await self._send_request(
            daemon.socket_path,
            "session.register",
            {"extensionId": "test-ext-123", "protocolVersion": "1.0"},
        )

        assert "result" in response
        assert response["result"]["status"] == "registered"
        assert response["result"]["sessionId"] == "test-ext-123"

    @pytest.mark.asyncio
    async def test_session_unregister(self, daemon):
        """Test session.unregister removes extension session."""
        # First register
        await self._send_request(
            daemon.socket_path,
            "session.register",
            {"extensionId": "test-ext-456"},
        )

        # Then unregister
        response = await self._send_request(
            daemon.socket_path,
            "session.unregister",
            {"extensionId": "test-ext-456"},
        )

        assert "result" in response
        assert response["result"]["status"] == "unregistered"

    @pytest.mark.asyncio
    async def test_tabs_list_with_no_extension(self, daemon):
        """Test tabs.list returns error when no extension connected."""
        response = await self._send_request(
            daemon.socket_path,
            "tabs.list",
            {},
        )

        assert "result" in response
        assert "error" in response["result"]
        assert "No extension connected" in response["result"]["error"]

    @pytest.mark.asyncio
    async def test_socket_permissions(self, daemon):
        """Test that socket has correct permissions."""
        import stat

        mode = daemon.socket_path.stat().st_mode
        # Check owner read/write (0600)
        assert mode & stat.S_IRUSR
        assert mode & stat.S_IWUSR
        # Check no group/other permissions
        assert not (mode & stat.S_IRGRP)
        assert not (mode & stat.S_IWGRP)
        assert not (mode & stat.S_IROTH)
        assert not (mode & stat.S_IWOTH)
