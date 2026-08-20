"""Tests for Native Messaging Host."""

import json
from pathlib import Path


class TestNativeMessagingHost:
    """Test Native Messaging Host functionality."""

    def test_native_host_script_exists(self):
        """Test that native host script exists."""
        host_script = (
            Path(__file__).parent.parent / "chrome_agent" / "native_host" / "native_host.py"
        )
        assert host_script.exists()

    def test_native_host_can_be_imported(self):
        """Test that native host module can be imported."""
        from chrome_agent.native_host.native_host import (
            get_socket_path,
        )

        # Test get_socket_path
        path = get_socket_path()
        assert path is not None
        assert "daemon.sock" in str(path)

    def test_extension_background_script_exists(self):
        """Test that extension background script exists."""
        script = Path(__file__).parent.parent / "extension" / "background.js"
        assert script.exists()

    def test_extension_content_script_exists(self):
        """Test that extension content script exists."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        assert script.exists()

    def test_extension_manifest_exists(self):
        """Test that extension manifest exists."""
        manifest = Path(__file__).parent.parent / "extension" / "manifest.json"
        assert manifest.exists()

        # Validate manifest
        with open(manifest) as f:
            data = json.load(f)

        assert data["manifest_version"] == 3
        assert "nativeMessaging" in data["permissions"]
        assert "scripting" in data["permissions"]
