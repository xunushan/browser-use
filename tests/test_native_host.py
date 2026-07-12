"""Tests for Native Messaging Host."""

import json
import socket
import struct
import subprocess
import sys
from pathlib import Path

import pytest


class TestNativeMessagingHost:
    """Test Native Messaging Host functionality."""

    def test_native_host_script_exists(self):
        """Test that native host script exists."""
        host_script = Path(__file__).parent.parent / "chrome_agent" / "native_host" / "native_host.py"
        assert host_script.exists()

    def test_manifest_json_exists(self):
        """Test that manifest json exists."""
        manifest = Path(__file__).parent.parent / "chrome_agent" / "native_host" / "com.browseruse.chrome_agent.json"
        assert manifest.exists()

    def test_native_host_can_be_imported(self):
        """Test that native host module can be imported."""
        from chrome_agent.native_host.native_host import (
            get_socket_path,
            read_native_message,
            write_native_message,
        )

        # Test get_socket_path
        path = get_socket_path()
        assert path is not None
        assert "daemon.sock" in str(path)

    def test_extension_background_script_exists(self):
        """Test that extension background script exists."""
        script = Path(__file__).parent.parent / "chrome_extension" / "background" / "background.js"
        assert script.exists()

    def test_extension_content_script_exists(self):
        """Test that extension content script exists."""
        script = Path(__file__).parent.parent / "chrome_extension" / "content_scripts" / "content.js"
        assert script.exists()

    def test_extension_manifest_exists(self):
        """Test that extension manifest exists."""
        manifest = Path(__file__).parent.parent / "chrome_extension" / "manifest_v3" / "manifest.json"
        assert manifest.exists()

        # Validate manifest
        import json
        with open(manifest) as f:
            data = json.load(f)

        assert data["manifest_version"] == 3
        assert "nativeMessaging" in data["permissions"]
        assert "scripting" in data["permissions"]
