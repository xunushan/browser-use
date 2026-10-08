"""Tests for Native Messaging Host."""

import io
import json
import socket
import struct
import sys
import types
from pathlib import Path

import pytest

from chrome_agent.native_host import native_host as host

# Half of an emoji — what JavaScript's JSON.stringify writes for a string that
# was cut between the two halves of one. UTF-8 cannot represent it.
LOOSE_HALF = "\ud83c"


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


def _framed(payload: bytes) -> bytes:
    return struct.pack("<I", len(payload)) + payload


def _read_frame(stream: io.BytesIO) -> dict:
    stream.seek(0)
    (length,) = struct.unpack("<I", stream.read(4))
    return json.loads(stream.read(length).decode("ascii"))


class TestOneBadMessageIsNotAnOutage:
    """A message the host cannot carry must not take the channel with it.

    The failure this guards: a snapshot holding half an emoji raised out of the
    read, killed the host process, and reached the caller as "Extension
    disconnected" — an outage caused by one message, described as something else.
    """

    def test_a_half_character_survives_the_trip_to_the_daemon(self):
        near, far = socket.socketpair()
        try:
            host.send_to_daemon(near, {"id": "1", "result": {"text": LOOSE_HALF}})

            (length,) = struct.unpack("<I", far.recv(4))
            payload = b""
            while len(payload) < length:
                payload += far.recv(length - len(payload))
        finally:
            near.close()
            far.close()

        # ASCII on the wire is the whole point: the escape is what makes it sendable.
        assert json.loads(payload.decode("ascii"))["result"]["text"] == LOOSE_HALF

    def test_a_half_character_survives_the_trip_back_to_chrome(self, monkeypatch):
        stdout = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", types.SimpleNamespace(buffer=stdout))

        host.write_native_message({"id": "1", "result": {"text": LOOSE_HALF}})

        assert _read_frame(stdout)["result"]["text"] == LOOSE_HALF

    def test_a_message_that_will_not_parse_leaves_the_stream_in_step(self, monkeypatch):
        good = b'{"jsonrpc": "2.0", "id": "2"}'
        monkeypatch.setattr(
            sys,
            "stdin",
            types.SimpleNamespace(buffer=io.BytesIO(_framed(b"not json") + _framed(good))),
        )

        with pytest.raises(host.UnreadableMessageError):
            host.read_native_message()

        # The next frame is read from where it actually starts, not from the
        # middle of the one that failed.
        assert host.read_native_message() == {"jsonrpc": "2.0", "id": "2"}

    def test_an_oversize_message_is_drained_before_the_next_one_is_read(self, monkeypatch):
        monkeypatch.setattr(host, "MAX_MESSAGE_BYTES", 8)
        monkeypatch.setattr(
            sys,
            "stdin",
            types.SimpleNamespace(
                buffer=io.BytesIO(_framed(b"123456789") + _framed(b'{"a":1}'))
            ),
        )

        with pytest.raises(host.UnreadableMessageError):
            host.read_native_message()

        assert host.read_native_message() == {"a": 1}

    def test_an_oversize_answer_names_the_request_it_belonged_to(self, monkeypatch):
        """So the caller hears why, instead of waiting out the timeout."""
        monkeypatch.setattr(host, "MAX_MESSAGE_BYTES", 8)
        frame = json.dumps({"jsonrpc": "2.0", "id": "9", "result": {"x": 1}}).encode()
        monkeypatch.setattr(
            sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(_framed(frame)))
        )

        with pytest.raises(host.UnreadableMessageError) as raised:
            host.read_native_message()

        assert raised.value.request_id == "9"

    def test_the_daemon_hears_which_request_failed(self):
        near, far = socket.socketpair()
        try:
            host._tell_daemon_it_failed(
                near, {"jsonrpc": "2.0", "id": "7", "result": {}}, ValueError("boom")
            )

            (length,) = struct.unpack("<I", far.recv(4))
            payload = b""
            while len(payload) < length:
                payload += far.recv(length - len(payload))
        finally:
            near.close()
            far.close()

        answer = json.loads(payload)
        assert answer["id"] == "7"
        assert "boom" in answer["error"]["message"]
