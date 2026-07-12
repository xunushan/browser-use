"""Test the control链路 without real Chrome.

This simulates an extension connecting to the daemon
and verifies the full CLI -> Daemon -> Extension flow.
"""

import asyncio
import json
import struct
import subprocess
import time

import pytest


class TestControlLink:
    """Test control链路 with mock extension."""

    @pytest.fixture(scope="module")
    def daemon_running(self):
        """Ensure daemon is running."""
        # Start daemon if not running
        result = subprocess.run(
            ["python", "-m", "chrome_agent.cli", "ensure", "--launch-if-missing"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and "already running" not in result.stdout:
            pytest.skip("Could not start daemon")

        yield True

        # Cleanup - stop daemon
        subprocess.run(
            ["python", "-m", "chrome_agent.cli", "stop"],
            capture_output=True,
        )

    def test_daemon_ready(self, daemon_running):
        """Test daemon responds to system.ready."""
        result = subprocess.run(
            ["python", "-m", "chrome_agent.cli", "ensure", "--json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["daemon"] is True

    def test_register_extension_session(self, daemon_running):
        """Test extension can register with daemon."""
        # Connect to daemon and register as extension
        import socket
        from pathlib import Path

        socket_path = Path.home() / ".chrome-agent" / "run" / "daemon.sock"

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(socket_path))

            # Send session.register
            request = {
                "jsonrpc": "2.0",
                "id": "test-register-1",
                "method": "session.register",
                "params": {
                    "extensionId": "test-extension-123",
                    "protocolVersion": "1.0",
                    "browserVersion": "Chrome/120.0.0.0",
                },
            }
            request_bytes = json.dumps(request).encode("utf-8")
            sock.sendall(struct.pack("<I", len(request_bytes)))
            sock.sendall(request_bytes)

            # Receive response
            length_bytes = sock.recv(4)
            message_length = struct.unpack("<I", length_bytes)[0]
            data = sock.recv(message_length)

            response = json.loads(data.decode("utf-8"))
            assert "result" in response
            assert response["result"]["status"] == "registered"
            assert response["result"]["sessionId"] == "test-extension-123"

        finally:
            sock.close()

    def test_tabs_list_after_registration(self, daemon_running):
        """Test tabs.list works after extension registers."""
        import socket
        from pathlib import Path

        socket_path = Path.home() / ".chrome-agent" / "run" / "daemon.sock"

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(socket_path))

            # Register extension first
            register_request = {
                "jsonrpc": "2.0",
                "id": "test-register-2",
                "method": "session.register",
                "params": {
                    "extensionId": "test-extension-456",
                },
            }
            request_bytes = json.dumps(register_request).encode("utf-8")
            sock.sendall(struct.pack("<I", len(request_bytes)))
            sock.sendall(request_bytes)

            # Read register response
            length_bytes = sock.recv(4)
            message_length = struct.unpack("<I", length_bytes)[0]
            sock.recv(message_length)

            # Now request tabs.list
            tabs_request = {
                "jsonrpc": "2.0",
                "id": "test-tabs-1",
                "method": "tabs.list",
                "params": {},
            }
            request_bytes = json.dumps(tabs_request).encode("utf-8")
            sock.sendall(struct.pack("<I", len(request_bytes)))
            sock.sendall(request_bytes)

            # Read tabs response
            length_bytes = sock.recv(4)
            message_length = struct.unpack("<I", length_bytes)[0]
            data = sock.recv(message_length)

            response = json.loads(data.decode("utf-8"))
            assert "result" in response
            # Should be forwarded to extension (mock)
            assert response["result"]["forwarded"] is True
            assert response["result"]["method"] == "tabs.list"

        finally:
            sock.close()

    def test_cli_tabs_list_with_extension(self, daemon_running):
        """Test CLI tabs list after extension registration."""
        # First register extension via direct socket
        import socket
        from pathlib import Path

        socket_path = Path.home() / ".chrome-agent" / "run" / "daemon.sock"

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(socket_path))
            register_request = {
                "jsonrpc": "2.0",
                "id": "test-register-3",
                "method": "session.register",
                "params": {"extensionId": "test-extension-789"},
            }
            request_bytes = json.dumps(register_request).encode("utf-8")
            sock.sendall(struct.pack("<I", len(request_bytes)))
            sock.sendall(request_bytes)

            # Read response
            length_bytes = sock.recv(4)
            message_length = struct.unpack("<I", length_bytes)[0]
            sock.recv(message_length)

        finally:
            sock.close()

        # Now test CLI
        result = subprocess.run(
            ["python", "-m", "chrome_agent.cli", "tabs", "list", "--json"],
            capture_output=True,
            text=True,
        )

        # Should get forwarded response
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "forwarded" in output
        assert output["method"] == "tabs.list"

    def test_full_xiaohongshu_flow_mock(self, daemon_running):
        """Test complete Xiaohongshu flow with mock extension.

        Simulates:
        1. Extension registers
        2. CLI lists tabs (finds xiaohongshu.com)
        3. CLI claims tab
        4. CLI takes snapshot
        5. CLI fills search box
        6. CLI presses Enter
        7. CLI waits for results
        8. CLI takes snapshot of results
        """
        import socket
        from pathlib import Path

        socket_path = Path.home() / ".chrome-agent" / "run" / "daemon.sock"

        # Register mock extension
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(socket_path))
            register_request = {
                "jsonrpc": "2.0",
                "id": "mock-register",
                "method": "session.register",
                "params": {"extensionId": "mock-xhs-extension"},
            }
            request_bytes = json.dumps(register_request).encode("utf-8")
            sock.sendall(struct.pack("<I", len(request_bytes)))
            sock.sendall(request_bytes)

            # Read response
            length_bytes = sock.recv(4)
            message_length = struct.unpack("<I", length_bytes)[0]
            sock.recv(message_length)

        finally:
            sock.close()

        # Test CLI commands
        commands = [
            ("tabs", "list", "--json"),
            ("tabs", "claim", "123", "--json"),
            ("page", "snapshot", "--tab-id", "123", "--json"),
            ("page", "fill", "--tab-id", "123", "--ref", "e12", "--value", "318攻略", "--json"),
            ("page", "keypress", "--tab-id", "123", "--keys", "Enter", "--json"),
            ("page", "wait", "--tab-id", "123", "--selector", ".search-results", "--json"),
        ]

        for cmd in commands:
            result = subprocess.run(
                ["python", "-m", "chrome_agent.cli"] + list(cmd),
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Command failed: {cmd}\n{result.stderr}"
            output = json.loads(result.stdout)
            assert "forwarded" in output, f"Expected forwarded response for {cmd}"
