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


def read_native_message() -> dict | None:
    prefix = _read_exact_stream(sys.stdin.buffer, 4)
    if prefix is None:
        return None
    length = struct.unpack("<I", prefix)[0]
    if length > MAX_MESSAGE_BYTES:
        raise ValueError(f"Chrome message exceeds {MAX_MESSAGE_BYTES} bytes")
    payload = _read_exact_stream(sys.stdin.buffer, length)
    return json.loads(payload.decode("utf-8")) if payload is not None else None


def write_native_message(message: dict) -> None:
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
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
        raise ValueError(f"Daemon message exceeds {MAX_MESSAGE_BYTES} bytes")
    payload = _read_exact_socket(sock, length)
    return json.loads(payload.decode("utf-8")) if payload is not None else None


def send_to_daemon(sock: socket.socket, message: dict) -> None:
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("<I", len(payload)) + payload)


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
            message = read_daemon_message(sock)
            if message is None:
                break
            write_native_message(message)
    except Exception:
        logger.exception("Daemon-to-Chrome bridge failed")
    finally:
        stopped.set()


def main() -> None:
    logger.info("Native Messaging Host started")
    stopped = threading.Event()
    sock: socket.socket | None = None
    try:
        sock = connect_to_daemon()
        reader = threading.Thread(target=_daemon_to_chrome, args=(sock, stopped), daemon=True)
        reader.start()

        while not stopped.is_set():
            message = read_native_message()
            if message is None:
                break
            send_to_daemon(sock, message)
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
