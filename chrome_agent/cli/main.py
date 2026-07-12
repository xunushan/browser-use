"""CLI for Chrome Agent."""

import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import click

from .. import __version__
from ..daemon import ChromeAgentDaemon
from ..utils.paths import get_lock_path, get_pid_path, get_socket_path


@click.group()
@click.version_option(version=__version__, prog_name="chrome-agent")
def cli():
    """Chrome Agent - Local browser automation system."""
    pass


@cli.command()
@click.option("--launch-if-missing", is_flag=True, help="Launch daemon if not running")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def ensure(launch_if_missing: bool, json_output: bool) -> None:
    """Ensure daemon is running."""
    try:
        # Try to connect to existing daemon
        result = _ping_daemon()
        if result:
            if json_output:
                click.echo(json.dumps({"status": "ready", "daemon": True}))
            else:
                click.echo("Daemon is running")
            return
    except Exception:
        pass

    if launch_if_missing:
        # Start daemon
        _start_daemon()
        # Wait for daemon to be ready
        for _ in range(10):
            try:
                result = _ping_daemon()
                if result:
                    if json_output:
                        click.echo(json.dumps({"status": "ready", "daemon": True}))
                    else:
                        click.echo("Daemon started and ready")
                    return
            except Exception:
                pass
            time.sleep(0.5)

        if json_output:
            click.echo(json.dumps({"status": "error", "message": "Failed to start daemon"}))
        else:
            click.echo("Failed to start daemon", err=True)
        sys.exit(1)
    else:
        if json_output:
            click.echo(json.dumps({"status": "error", "message": "Daemon not running"}))
        else:
            click.echo("Daemon not running", err=True)
        sys.exit(1)


@cli.command()
def start() -> None:
    """Start the daemon."""
    try:
        _start_daemon()
        click.echo("Daemon started")
    except Exception as e:
        click.echo(f"Failed to start daemon: {e}", err=True)
        sys.exit(1)


@cli.command()
def stop() -> None:
    """Stop the daemon."""
    try:
        # Send stop command to daemon
        result = _send_command("system.stop", {})
        if result:
            click.echo("Daemon stopped")
        else:
            click.echo("Daemon not running")
    except Exception as e:
        click.echo(f"Failed to stop daemon: {e}", err=True)
        sys.exit(1)


@cli.command()
def status() -> None:
    """Check daemon status."""
    try:
        result = _ping_daemon()
        if result:
            click.echo(f"Daemon is running (protocol: {result.get('protocolVersion', 'unknown')})")
        else:
            click.echo("Daemon not running")
    except Exception:
        click.echo("Daemon not running")


@cli.command()
def version() -> None:
    """Show version information."""
    click.echo(f"Chrome Agent {__version__}")


def _ping_daemon() -> dict:
    """Ping the daemon and return response."""
    return _send_command("system.ping", {})


def _send_command(method: str, params: dict) -> dict:
    """Send a command to the daemon and return response."""
    socket_path = get_socket_path()

    if not socket_path.exists():
        raise ConnectionError("Daemon socket not found")

    # Connect to daemon
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(socket_path))

        # Send request
        request = {
            "jsonrpc": "2.0",
            "id": "cli-1",
            "method": method,
            "params": params,
        }
        request_bytes = json.dumps(request).encode("utf-8")
        sock.sendall(struct.pack("<I", len(request_bytes)))
        sock.sendall(request_bytes)

        # Receive response
        # Read length
        length_bytes = sock.recv(4)
        if not length_bytes:
            raise ConnectionError("No response from daemon")

        message_length = struct.unpack("<I", length_bytes)[0]
        data = sock.recv(message_length)

        response = json.loads(data.decode("utf-8"))
        if "error" in response:
            raise RuntimeError(response["error"]["message"])

        return response.get("result", {})
    finally:
        sock.close()


def _start_daemon() -> None:
    """Start the daemon process."""
    import fcntl

    lock_path = get_lock_path()
    lock_file = open(str(lock_path), "w")

    try:
        # Try to acquire lock
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            # Double-check if daemon is already running
            try:
                result = _ping_daemon()
                if result:
                    return
            except Exception:
                pass

            # Start daemon in background
            daemon_module = "chrome_agent.daemon.server"
            subprocess.Popen(
                [sys.executable, "-m", daemon_module],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            # Wait a moment for daemon to start
            time.sleep(1)

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def main() -> None:
    """Main entry point for CLI."""
    cli()
