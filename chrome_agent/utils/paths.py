"""Utility functions for Chrome Agent."""

import os
import platform
from pathlib import Path


def get_runtime_dir() -> Path:
    """Get the runtime directory for Chrome Agent."""
    system = platform.system()
    if system == "Linux":
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
        if xdg_runtime:
            path = Path(xdg_runtime) / "chrome-agent"
        else:
            path = Path.home() / ".local" / "run" / "chrome-agent"
    else:
        # macOS, and the Windows fallback (not supported in V1). The socket goes
        # in the install home rather than in a dot directory of its own so that
        # one directory holds the whole installation.
        path = get_home_dir() / "run"

    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def get_data_dir() -> Path:
    """Get the data directory for Chrome Agent."""
    system = platform.system()
    if system == "Darwin":
        path = Path.home() / "Library" / "Application Support" / "ChromeAgent"
    elif system == "Linux":
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            path = Path(xdg_data) / "chrome-agent"
        else:
            path = Path.home() / ".local" / "share" / "chrome-agent"
    else:
        path = get_home_dir()

    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def get_log_dir() -> Path:
    """Get the log directory for Chrome Agent."""
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_dir.chmod(0o700)
    return log_dir


def get_home_dir() -> Path:
    """Get the install home, which setup.sh calls $CHROME_AGENT_HOME.

    The virtualenv, the launcher, install.json and the copy of the extension
    Chrome loads all live here rather than in the checkout: the checkout is what
    the runtime is built from, not where it runs, so it may be moved or deleted
    once setup.sh has run. The extension copy has a reason of its own — Chrome
    remembers the path it loaded the extension from, and that path has to
    outlive an update.

    Deliberately not a dot directory. The one step of the install that needs a
    person is picking this folder in Chrome's "Load unpacked" dialog, and macOS
    file dialogs do not list dot directories at all — a hidden home cannot be
    chosen there, by any route a user would think to try.
    """
    override = os.environ.get("CHROME_AGENT_HOME")
    return Path(override) if override else Path.home() / "chrome-agent"


def get_extension_dir() -> Path:
    """Get the directory the extension is loaded from."""
    return get_home_dir() / "extension"


def get_install_record_path() -> Path:
    """Get the file setup.sh records this installation in."""
    return get_home_dir() / "install.json"


def get_socket_path() -> Path:
    """Get the Unix socket path for the daemon."""
    return get_runtime_dir() / "daemon.sock"


def get_lock_path() -> Path:
    """Get the lock file path for the daemon."""
    return get_runtime_dir() / "daemon.lock"


def get_pid_path() -> Path:
    """Get the PID file path for the daemon."""
    return get_runtime_dir() / "daemon.pid"
