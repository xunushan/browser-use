#!/usr/bin/env python3
"""Persistent full-duplex bridge between Chrome Native Messaging and the daemon.

Chrome owns this process.  Messages on stdin/stdout and on the daemon Unix socket
use the same four-byte little-endian length-prefixed JSON framing.  Keeping one
socket open for the lifetime of the native port is essential: the daemon uses it
to push Agent commands to the extension as well as to receive responses.
"""

from __future__ import annotations

import json
import logging
import socket
import struct
import subprocess
import sys
import threading
import time
from contextlib import suppress
from typing import BinaryIO

# The daemon and the CLI both take these paths from one place. This module used
# to spell them out for itself, which is how it kept talking to a socket the
# daemon no longer listened on after the install home moved.
from ..utils.paths import get_log_dir, get_socket_path

MAX_MESSAGE_BYTES = 10 * 1024 * 1024
_stdout_lock = threading.Lock()


class UnreadableMessageError(Exception):
    """One message is unusable and the stream is still in step for the next.

    Distinct from a channel failure on purpose. A frame whose JSON will not
    parse, or one longer than this host will carry, used to raise straight out
    of the read and take the process with it — which Chrome reports to the
    extension as a port that closed, and the daemon reports to the caller as
    "Extension disconnected". One bad message became an outage, described as
    something else entirely.

    Carries the request it was answering, when the frame was readable enough to
    say. Without it the caller waits out the forwarding timeout for a reply that
    was never coming; with it, the caller is told what happened.
    """

    def __init__(self, message: str, request_id: str | None = None):
        super().__init__(message)
        self.request_id = request_id


def setup_logging() -> None:
    log_dir = get_log_dir()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "native-host.log"),
            logging.StreamHandler(sys.stderr),
        ],
    )


setup_logging()
logger = logging.getLogger(__name__)


def _read_exact_stream(stream: BinaryIO, size: int) -> bytes | None:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


def _read_exact_socket(sock: socket.socket, size: int) -> bytes | None:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


def _request_id(payload: bytes | None) -> str | None:
    """The id of the request this frame answers, if the frame still says.

    Only used for frames that will not be forwarded whole — a huge one is still
    a readable one this side of the limit, and its id is all the daemon needs to
    fail the right caller.
    """
    try:
        answer = json.loads((payload or b"").decode("utf-8", "replace"))
        return answer.get("id")
    except (AttributeError, ValueError):
        return None


def read_native_message() -> dict | None:
    prefix = _read_exact_stream(sys.stdin.buffer, 4)
    if prefix is None:
        return None
    length = struct.unpack("<I", prefix)[0]
    if length > MAX_MESSAGE_BYTES:
        # Drain the frame before giving up on it: the next length header is only
        # where it belongs if every byte of this one is gone.
        payload = _read_exact_stream(sys.stdin.buffer, length)
        raise UnreadableMessageError(
            f"Chrome sent {length} bytes, over the {MAX_MESSAGE_BYTES} byte limit",
            request_id=_request_id(payload),
        )
    payload = _read_exact_stream(sys.stdin.buffer, length)
    if payload is None:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnreadableMessageError(f"Chrome sent unreadable JSON: {error}") from error


def write_native_message(message: dict) -> None:
    payload = _encode(message)
    with _stdout_lock:
        sys.stdout.buffer.write(struct.pack("<I", len(payload)))
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()


def read_daemon_message(sock: socket.socket) -> dict | None:
    prefix = _read_exact_socket(sock, 4)
    if prefix is None:
        return None
    length = struct.unpack("<I", prefix)[0]
    if length > MAX_MESSAGE_BYTES:
        _read_exact_socket(sock, length)
        raise UnreadableMessageError(
            f"The daemon sent {length} bytes, over the {MAX_MESSAGE_BYTES} byte limit"
        )
    payload = _read_exact_socket(sock, length)
    if payload is None:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnreadableMessageError(f"The daemon sent unreadable JSON: {error}") from error


def send_to_daemon(sock: socket.socket, message: dict) -> None:
    payload = _encode(message)
    sock.sendall(struct.pack("<I", len(payload)) + payload)


def _encode(message: dict) -> bytes:
    """Serialize a message for the wire, whatever characters are in it.

    ensure_ascii is not a formatting preference here. JavaScript's JSON.stringify
    writes a lone surrogate — half of an emoji, from a string that got cut in
    two somewhere — as the escape ``"\\ud83c"``, and ``json.loads`` hands that
    half character straight through as a lone surrogate. UTF-8 has no encoding
    for one, so re-serializing with the characters themselves raises
    UnicodeEncodeError. Escaping instead makes every message that parsed at all
    sendable; the receiver's own json.dumps would have written those escapes
    anyway, so nothing readable is lost.
    """
    return json.dumps(message, ensure_ascii=True).encode("utf-8")


def connect_to_daemon() -> socket.socket:
    path = get_socket_path()
    if not path.exists():
        subprocess.Popen(
            [sys.executable, "-m", "chrome_agent.daemon.server"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + 5
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
    if not path.exists():
        raise ConnectionError(f"Daemon did not create its socket: {path}")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(path))
    return sock


def _daemon_to_chrome(sock: socket.socket, stopped: threading.Event) -> None:
    try:
        while not stopped.is_set():
            try:
                message = read_daemon_message(sock)
            except UnreadableMessageError as error:
                logger.warning("%s; dropping it", error)
                continue
            if message is None:
                break
            write_native_message(message)
    except Exception:
        logger.exception("Daemon-to-Chrome bridge failed")
    finally:
        stopped.set()


def _tell_daemon_it_failed(sock: socket.socket, message: dict, error: Exception) -> None:
    """Answer a request the daemon is waiting on, since it will get no answer.

    Its id is all that is needed: the daemon matches this to the caller that
    asked, which then hears what went wrong instead of waiting out the
    forwarding timeout and being told the extension disconnected.
    """
    if message.get("id") is None:
        return
    with suppress(Exception):
        send_to_daemon(
            sock,
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {
                    "code": -32603,
                    "message": f"Message from the extension could not be forwarded: {error}",
                },
            },
        )


def main() -> None:
    logger.info("Native Messaging Host started")
    stopped = threading.Event()
    sock: socket.socket | None = None
    try:
        sock = connect_to_daemon()
        reader = threading.Thread(target=_daemon_to_chrome, args=(sock, stopped), daemon=True)
        reader.start()

        while not stopped.is_set():
            try:
                message = read_native_message()
            except UnreadableMessageError as error:
                logger.warning("%s; dropping it", error)
                if error.request_id is not None:
                    _tell_daemon_it_failed(sock, {"id": error.request_id}, error)
                continue
            if message is None:
                break
            try:
                send_to_daemon(sock, message)
            except OSError:
                # The socket itself is gone, so there is nothing left to bridge.
                raise
            except Exception as error:
                logger.exception("Could not forward a message from Chrome")
                _tell_daemon_it_failed(sock, message, error)
    except Exception:
        logger.exception("Native Messaging Host failed")
    finally:
        stopped.set()
        if sock is not None:
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            sock.close()
        logger.info("Native Messaging Host stopped")


if __name__ == "__main__":
    main()
