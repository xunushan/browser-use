"""CLI for Chrome Agent."""

import json
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import click

from .. import __version__
from ..utils.paths import get_lock_path, get_socket_path


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
def ensure(
    launch_if_missing: bool,
    wait_for_extension: bool,
    timeout: int,
    json_output: bool,
) -> None:
    """Ensure daemon and Chrome are running."""
    daemon_ready = False
    try:
        result = _check_daemon_ready()
        daemon_ready = bool(result)
    except Exception:
        pass

    if not daemon_ready and launch_if_missing:
        _start_daemon()
        daemon_ready = True
    if launch_if_missing and not _is_chrome_running():
        _launch_chrome()

    if daemon_ready:
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = _check_daemon_ready()
                if result:
                    extensions = result.get("extensions", [])
                    if extensions or not wait_for_extension:
                        if json_output:
                            click.echo(
                                json.dumps(
                                    {
                                        "status": "ready",
                                        "daemon": True,
                                        "chrome": _is_chrome_running(),
                                        "extension": bool(extensions),
                                        "extensions": extensions,
                                    }
                                )
                            )
                        else:
                            click.echo("Daemon is ready")
                        return
            except Exception:
                pass
            time.sleep(1)

        message = "Timeout waiting for Chrome extension"
    else:
        message = "Daemon not running; retry with --launch-if-missing"

    if json_output:
        click.echo(
            json.dumps(
                {
                    "status": "error",
                    "message": message,
                    "daemon": daemon_ready,
                    "chrome": _is_chrome_running(),
                    "extension": False,
                }
            )
        )
    else:
        click.echo(message, err=True)
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


def _launch_chrome() -> None:
    """Launch the system Chrome without creating a separate profile."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-a", "Google Chrome"])
    elif sys.platform == "linux":
        subprocess.Popen(["google-chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
                    click.echo(
                        f"{active} [{tab['id']}] {tab.get('title', 'Untitled')}"
                        f" - {tab.get('url', '')}"
                    )
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


@tabs.command("navigate")
@click.argument("tab_id", type=int)
@click.argument("url")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def tabs_navigate(tab_id: int, url: str, json_output: bool) -> None:
    """Navigate an existing tab to an HTTP(S) URL."""
    try:
        result = _send_command("tabs.navigate", {"tabId": tab_id, "url": url})
        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Navigated tab {tab_id} to {result.get('url', url)}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@tabs.command("activate")
@click.argument("tab_id", type=int)
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def tabs_activate(tab_id: int, json_output: bool) -> None:
    """Activate a tab and focus its Chrome window."""
    try:
        result = _send_command("tabs.activate", {"tabId": tab_id})
        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Activated tab: {result.get('tabId')}")
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
@click.option("--ref", help="Element ref whose nearest scroll container should move")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_scroll(tab_id: int, dx: int, dy: int, ref: str, json_output: bool) -> None:
    """Scroll page."""
    try:
        params = {"tabId": tab_id, "dx": dx, "dy": dy}
        if ref:
            params["ref"] = ref
        result = _send_command("page.scroll", params)

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


@page.command("validate")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", required=True, help="Element reference")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_validate(tab_id: int, ref: str, json_output: bool) -> None:
    """Validate element state."""
    try:
        result = _send_command("page.validate", {"tabId": tab_id, "ref": ref})

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Validation for {ref} on tab {tab_id}: {result}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("screenshot")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--scope", default="viewport", help="Screenshot scope (viewport/element)")
@click.option("--ref", help="Element reference for element scope")
@click.option("--output", "output_path", help="Output file path")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_screenshot(tab_id: int, scope: str, ref: str, output_path: str, json_output: bool) -> None:
    """Take a screenshot of a tab or element."""
    try:
        params = {"tabId": tab_id, "scope": scope}
        if ref:
            params["ref"] = ref

        result = _send_command("page.screenshot", params)

        if output_path and result.get("screenshot"):
            import base64

            data_url = result["screenshot"]
            if "," in data_url:
                _, b64 = data_url.split(",", 1)
            else:
                b64 = data_url
            Path(output_path).write_bytes(base64.b64decode(b64))

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Screenshot of tab {tab_id} (scope: {scope})")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("extract")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_extract(tab_id: int, json_output: bool) -> None:
    """Extract structured data from a page."""
    try:
        result = _send_command("page.extract", {"tabId": tab_id})

        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Extracted data from tab {tab_id}")
            click.echo(f"  Links: {len(result.get('links', []))}")
            click.echo(f"  Images: {len(result.get('images', []))}")
            click.echo(f"  Headings: {len(result.get('headings', []))}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("text")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", required=True, help="Text container element reference")
@click.option(
    "--max-chars",
    default=20000,
    type=click.IntRange(1, 200000),
    help="Maximum characters to return",
)
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_text(tab_id: int, ref: str, max_chars: int, json_output: bool) -> None:
    """Extract full visible text from a referenced element."""
    try:
        result = _send_command(
            "page.text",
            {"tabId": tab_id, "ref": ref, "maxChars": max_chars},
        )
        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(result.get("text", ""))
            if result.get("truncated"):
                click.echo(
                    f"[truncated: returned {result.get('returnedLength')}"
                    f" of {result.get('length')} characters]",
                    err=True,
                )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("images")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", help="Limit discovery to this element and its descendants")
@click.option("--load", is_flag=True, help="Scroll to trigger lazy-loaded images")
@click.option("--max-scrolls", default=12, type=click.IntRange(0, 100))
@click.option("--settle-ms", default=500, type=click.IntRange(0, 10000))
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_images(
    tab_id: int,
    ref: str,
    load: bool,
    max_scrolls: int,
    settle_ms: int,
    json_output: bool,
) -> None:
    """Discover currentSrc, srcset and CSS background images."""
    try:
        params = {
            "tabId": tab_id,
            "load": load,
            "maxScrolls": max_scrolls,
            "settleMs": settle_ms,
        }
        if ref:
            params["ref"] = ref
        result = _send_command("page.images", params)
        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Discovered {result.get('count', 0)} images on tab {tab_id}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("download-images")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", help="Limit downloads to this element and its descendants")
@click.option(
    "--url",
    "urls",
    multiple=True,
    help="Exact discovered image URL to download (repeatable; requires --ref)",
)
@click.option("--load", is_flag=True, help="Scroll to trigger lazy-loaded images")
@click.option("--limit", default=20, type=click.IntRange(1, 100))
@click.option("--max-scrolls", default=12, type=click.IntRange(0, 100))
@click.option("--settle-ms", default=500, type=click.IntRange(0, 10000))
@click.option(
    "--timeout",
    default=30,
    type=click.IntRange(1, 120),
    help="Per-download wait in seconds",
)
@click.option(
    "--prefix",
    default="image",
    help="Safe filename prefix inside Downloads/chrome-agent",
)
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_download_images(
    tab_id: int,
    ref: str,
    urls: tuple[str, ...],
    load: bool,
    limit: int,
    max_scrolls: int,
    settle_ms: int,
    timeout: int,
    prefix: str,
    json_output: bool,
) -> None:
    """Load and download page images through the user's Chrome profile."""
    try:
        result = _send_command(
            "page.downloadImages",
            {
                "tabId": tab_id,
                "ref": ref,
                "urls": list(urls),
                "load": load,
                "limit": limit,
                "maxScrolls": max_scrolls,
                "settleMs": settle_ms,
                "timeoutMs": timeout * 1000,
                "prefix": prefix,
            },
        )
        if json_output:
            click.echo(json.dumps(result))
        else:
            completed = sum(item.get("state") == "complete" for item in result.get("downloads", []))
            click.echo(f"Downloaded {completed}/{result.get('requested', 0)} images")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("media")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", help="Limit discovery to this media container")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_media(tab_id: int, ref: str, json_output: bool) -> None:
    """Discover video/audio elements and structured media URLs."""
    try:
        params = {"tabId": tab_id}
        if ref:
            params["ref"] = ref
        result = _send_command("page.media", params)
        if json_output:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Discovered {result.get('count', 0)} media resources")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@page.command("download-media")
@click.option("--tab-id", type=int, required=True, help="Tab ID")
@click.option("--ref", help="Limit downloads to this media container")
@click.option("--limit", default=10, type=click.IntRange(1, 50))
@click.option("--timeout", default=120, type=click.IntRange(1, 600))
@click.option("--prefix", default="media", help="Filename prefix under Downloads/chrome-agent")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def page_download_media(
    tab_id: int,
    ref: str,
    limit: int,
    timeout: int,
    prefix: str,
    json_output: bool,
) -> None:
    """Download directly addressable video/audio through Chrome."""
    try:
        params = {
            "tabId": tab_id,
            "limit": limit,
            "timeoutMs": timeout * 1000,
            "prefix": prefix,
        }
        if ref:
            params["ref"] = ref
        result = _send_command("page.downloadMedia", params)
        if json_output:
            click.echo(json.dumps(result))
        else:
            completed = sum(item.get("state") == "complete" for item in result.get("downloads", []))
            click.echo(f"Downloaded {completed}/{result.get('downloadable', 0)} media resources")
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
        length_bytes = _recv_exact(sock, 4)
        if not length_bytes:
            raise ConnectionError("No response from daemon")

        message_length = struct.unpack("<I", length_bytes)[0]
        data = _recv_exact(sock, message_length)

        response = json.loads(data.decode("utf-8"))
        if "error" in response:
            raise RuntimeError(response["error"]["message"])

        return response.get("result", {})
    finally:
        sock.close()


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    """Read exactly one framed payload from a local socket."""
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("Daemon closed the connection")
        chunks.extend(chunk)
    return bytes(chunks)


def _start_daemon() -> None:
    """Start the daemon process."""
    import fcntl

    lock_path = get_lock_path()
    with open(lock_path, "w") as lock_file:
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


def main() -> None:
    """Main entry point for CLI."""
    cli()
