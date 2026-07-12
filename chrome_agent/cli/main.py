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
@click.option("--launch-if-missing", is_flag=True, help="Launch Chrome if not running")
@click.option("--wait-for-extension", is_flag=True, help="Wait for extension to connect")
@click.option("--timeout", default=30, type=int, help="Timeout in seconds")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def ensure(launch_if_missing: bool, wait_for_extension: bool, timeout: int, json_output: bool) -> None:
    """Ensure daemon and Chrome are running."""
    try:
        # Try to connect to existing daemon
        result = _check_daemon_ready()
        if result:
            # Check if extension is connected
            extensions = result.get("extensions", [])
            if extensions or not wait_for_extension:
                if json_output:
                    click.echo(json.dumps({
                        "status": "ready",
                        "daemon": True,
                        "chrome": True,
                        "extension": len(extensions) > 0,
                        "extensions": extensions,
                    }))
                else:
                    click.echo("Daemon is running")
                    if extensions:
                        click.echo(f"Extension connected: {extensions[0]}")
                return
    except Exception:
        pass

    if launch_if_missing:
        # Start daemon
        _start_daemon()

        # Wait for daemon to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = _check_daemon_ready()
                if result:
                    if not wait_for_extension:
                        if json_output:
                            click.echo(json.dumps({
                                "status": "ready",
                                "daemon": True,
                                "chrome": _is_chrome_running(),
                            }))
                        else:
                            click.echo("Daemon started and ready")
                        return

                    # Wait for extension
                    extensions = result.get("extensions", [])
                    if extensions:
                        if json_output:
                            click.echo(json.dumps({
                                "status": "ready",
                                "daemon": True,
                                "chrome": True,
                                "extension": True,
                                "extensions": extensions,
                            }))
                        else:
                            click.echo("Daemon and extension ready")
                        return
            except Exception:
                pass
            time.sleep(1)

        if json_output:
            click.echo(json.dumps({
                "status": "error",
                "message": "Timeout waiting for daemon/extension",
                "daemon": _ping_daemon() is not None,
                "chrome": _is_chrome_running(),
            }))
        else:
            click.echo("Timeout waiting for daemon/extension", err=True)
        sys.exit(1)
    else:
        if json_output:
            click.echo(json.dumps({
                "status": "error",
                "message": "Daemon not running",
            }))
        else:
            click.echo("Daemon not running", err=True)
        sys.exit(1)


def _is_chrome_running() -> bool:
    """Check if Chrome is running."""
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["pgrep", "-x", "Google Chrome"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        elif sys.platform == "linux":
            result = subprocess.run(
                ["pgrep", "google-chrome"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        return False
    except Exception:
        return False


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


@cli.group()
def tabs():
    """Tab management commands."""
    pass


@tabs.command("list")
@click.option("--domain", help="Filter by domain")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def tabs_list(domain: str, json_output: bool) -> None:
    """List browser tabs."""
    try:
        params = {}
        if domain:
            params["domain"] = domain

        result = _send_command("tabs.list", params)

        if json_output:
            click.echo(json.dumps(result))
        else:
            if "error" in result:
                click.echo(f"Error: {result['error']}", err=True)
                sys.exit(1)
            else:
                tabs = result.get("tabs", [])
                for tab in tabs:
                    active = "*" if tab.get("active") else " "
                    click.echo(f"{active} [{tab['id']}] {tab.get('title', 'Untitled')} - {tab.get('url', '')}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@tabs.command("open")
@click.argument("url")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def tabs_open(url: str, json_output: bool) -> None:
    """Open a new tab."""
    try:
        result = _send_command("tabs.open", {"url": url})

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Opened tab: {result.get('tabId')} - {result.get('url')}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@tabs.command("claim")
@click.argument("tab_id", type=int)
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def tabs_claim(tab_id: int, json_output: bool) -> None:
    """Claim a tab for control."""
    try:
        result = _send_command("tabs.claim", {"tabId": tab_id})

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Claimed tab: {result.get('tabId')} - {result.get('title', '')}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def page():
    """Page interaction commands."""
    pass


@page.command("snapshot")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--scope", default="viewport", help="Snapshot scope (viewport/full/element)")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_snapshot(tab_id: int, scope: str, json_output: bool) -> None:
    """Take a DOM snapshot."""
    try:
        result = _send_command("page.snapshot", {"tabId": tab_id, "scope": scope})

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Snapshot of tab {tab_id} (scope: {scope})")
            if "elements" in result:
                click.echo(f"Found {len(result['elements'])} elements")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("click")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", required=True, help="Element reference")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_click(tab_id: int, ref: str, json_output: bool) -> None:
    """Click an element."""
    try:
        result = _send_command("page.click", {"tabId": tab_id, "ref": ref})

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Clicked element {ref} on tab {tab_id}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("fill")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", required=True, help="Element reference")
@click.option("--value", required=True, help="Value to fill")
@click.option("--secret-stdin", is_flag=True, help="Read value from stdin (sensitive)")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_fill(tab_id: int, ref: str, value: str, secret_stdin: bool, json_output: bool) -> None:
    """Fill an element."""
    try:
        if secret_stdin:
            import getpass
            value = getpass.getpass("Enter value: ")

        result = _send_command("page.fill", {"tabId": tab_id, "ref": ref, "value": value})

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Filled element {ref} on tab {tab_id}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("keypress")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", help="Element reference (optional)")
@click.option("--keys", required=True, help="Keys to press")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_keypress(tab_id: int, ref: str, keys: str, json_output: bool) -> None:
    """Send keypress to an element."""
    try:
        params = {"tabId": tab_id, "keys": keys}
        if ref:
            params["ref"] = ref

        result = _send_command("page.keypress", params)

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Sent keypress '{keys}' to tab {tab_id}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("scroll")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--dx", default=0, type=int, help="Horizontal scroll amount")
@click.option("--dy", default=0, type=int, help="Vertical scroll amount")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_scroll(tab_id: int, dx: int, dy: int, json_output: bool) -> None:
    """Scroll page."""
    try:
        result = _send_command("page.scroll", {"tabId": tab_id, "dx": dx, "dy": dy})

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Scrolled tab {tab_id} by ({dx}, {dy})")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("wait")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--selector", help="CSS selector to wait for")
@click.option("--url", help="URL to wait for")
@click.option("--timeout", default=5000, type=int, help="Timeout in milliseconds")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_wait(tab_id: int, selector: str, url: str, timeout: int, json_output: bool) -> None:
    """Wait for condition."""
    try:
        params = {"tabId": tab_id, "timeout": timeout}
        if selector:
            params["selector"] = selector
        if url:
            params["url"] = url

        result = _send_command("page.wait", params)

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Wait completed for tab {tab_id}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def version() -> None:
    """Show version information."""
    click.echo(f"Chrome Agent {__version__}")


def _ping_daemon() -> dict:
    """Ping the daemon and return response."""
    return _send_command("system.ping", {})


def _check_daemon_ready() -> dict:
    """Check daemon ready status and return response."""
    return _send_command("system.ready", {})


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
