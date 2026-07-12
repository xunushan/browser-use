#!/usr/bin/env python3
"""Native Messaging Host for Chrome Agent.

This script is launched by Chrome when the extension calls chrome.runtime.connectNative().
It bridges the Native Messaging protocol (length-prefixed JSON) with the daemon's
Unix Socket (also length-prefixed JSON-RPC).
"""

import json
import logging
import os
import socket
import struct
import sys
import time
from pathlib import Path

def setup_logging() -> None:
    """Set up logging for the native host."""
    log_dir = Path.home() / ".chrome-agent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(str(log_dir / "native-host.log")),
            logging.StreamHandler(sys.stderr),
        ],
    )


# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


def get_socket_path() -> Path:
    """Get the Unix socket path for the daemon."""
    return Path.home() / ".chrome-agent" / "run" / "daemon.sock"


def read_native_message() -> dict:
    """Read a message from Chrome using Native Messaging protocol."""
    # Read message length (4 bytes, little-endian)
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return None

    message_length = struct.unpack("<I", raw_length)[0]

    # Read message data
    data = sys.stdin.buffer.read(message_length)
    if len(data) != message_length:
        logger.warning("Incomplete message received")
        return None

    return json.loads(data.decode("utf-8"))


def write_native_message(message: dict) -> None:
    """Write a message to Chrome using Native Messaging protocol."""
    data = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def connect_to_daemon() -> socket.socket:
    """Connect to the Chrome Agent Daemon via Unix Socket."""
    socket_path = get_socket_path()

    if not socket_path.exists():
        logger.error(f"Daemon socket not found: {socket_path}")
        raise ConnectionError("Daemon not running")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(socket_path))
    return sock


def read_daemon_response(sock: socket.socket) -> dict:
    """Read a response from the daemon."""
    # Read message length (4 bytes, little-endian)
    length_bytes = sock.recv(4)
    if not length_bytes:
        return None

    message_length = struct.unpack("<I", length_bytes)[0]

    # Read message data
    data = sock.recv(message_length)
    if len(data) != message_length:
        logger.warning("Incomplete response from daemon")
        return None

    return json.loads(data.decode("utf-8"))


def forward_to_daemon(message: dict) -> dict:
    """Forward a message to the daemon and return the response."""
    sock = None
    try:
        sock = connect_to_daemon()

        # Send message to daemon
        data = json.dumps(message).encode("utf-8")
        sock.sendall(struct.pack("<I", len(data)))
        sock.sendall(data)

        # Read response from daemon
        response = read_daemon_response(sock)
        return response

    except Exception as e:
        logger.error(f"Error forwarding to daemon: {e}")
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {
                "code": -32000,
                "message": f"Daemon communication error: {e}",
            },
        }
    finally:
        if sock:
            sock.close()


def main():
    """Main entry point for Native Messaging Host."""
    logger.info("Native Messaging Host started")

    try:
        while True:
            # Read message from Chrome
            message = read_native_message()
            if message is None:
                logger.info("Chrome closed connection")
                break

            logger.info(f"Received from Chrome: {message.get('method', 'unknown')}")

            # Forward to daemon and get response
            response = forward_to_daemon(message)

            # Write response to Chrome
            write_native_message(response)
            logger.info(f"Sent response to Chrome: {response.get('result', 'error')}")

    except KeyboardInterrupt:
        logger.info("Native Messaging Host interrupted")
    except Exception as e:
        logger.error(f"Native Messaging Host error: {e}")
    finally:
        logger.info("Native Messaging Host exiting")


if __name__ == "__main__":
    main()
