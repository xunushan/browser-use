"""Test utilities and helpers for integration tests."""

import asyncio
import json
import socket
import struct
from pathlib import Path

import pytest

from chrome_agent.daemon.daemon import ChromeAgentDaemon


class TestClient:
    """Test client for communicating with daemon."""

    def __init__(self, socket_path: Path):
        self.socket_path = socket_path

    async def send_request(self, method: str, params: dict, request_id: str = "test-1") -> dict:
        """Send JSON-RPC request to daemon."""
        reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
        try:
            request = {
                "jsonrpc": "2.0",
                "id": request_id,
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


class MockChromeExtension:
    """Mock Chrome extension for testing."""

    def __init__(self):
        self.connected = False
        self.tabs = []
        self.injected_scripts = {}

    def connect(self):
        """Simulate extension connection."""
        self.connected = True
        return {"status": "connected"}

    def disconnect(self):
        """Simulate extension disconnection."""
        self.connected = False

    def add_tab(self, tab_id: int, url: str, title: str):
        """Add a mock tab."""
        self.tabs.append({
            "id": tab_id,
            "url": url,
            "title": title,
        })

    def inject_script(self, tab_id: int):
        """Simulate script injection."""
        self.injected_scripts[tab_id] = {
            "injected_at": asyncio.get_event_loop().time(),
            "document_id": f"doc-{tab_id}",
        }

    def get_tab(self, tab_id: int) -> dict:
        """Get tab by ID."""
        for tab in self.tabs:
            if tab["id"] == tab_id:
                return tab
        return None


class MockPageContext:
    """Mock page context for testing auth detection."""

    def __init__(self, url: str, title: str, elements: list = None):
        self.url = url
        self.title = title
        self.elements = elements or []

    def add_element(self, element_type: str, **kwargs):
        """Add an element to the page context."""
        element = {"type": element_type}
        element.update(kwargs)
        self.elements.append(element)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "title": self.title,
            "elements": self.elements,
        }


@pytest.fixture
async def test_daemon():
    """Create and start a test daemon."""
    daemon = ChromeAgentDaemon()
    daemon.socket_path = Path.home() / ".chrome-agent" / "run" / "test-daemon.sock"

    # Remove old socket
    if daemon.socket_path.exists():
        daemon.socket_path.unlink()

    task = asyncio.create_task(daemon.start())

    # Wait for daemon to be ready
    for _ in range(20):
        if daemon.running:
            break
        await asyncio.sleep(0.1)

    yield daemon

    # Cleanup
    await daemon.stop()
    if daemon.socket_path.exists():
        daemon.socket_path.unlink()


@pytest.fixture
def test_client(test_daemon):
    """Create a test client connected to the daemon."""
    return TestClient(test_daemon.socket_path)


@pytest.fixture
def mock_extension():
    """Create a mock Chrome extension."""
    return MockChromeExtension()


@pytest.fixture
def mock_page():
    """Create a mock page context."""
    return MockPageContext("https://example.com", "Example Page")
