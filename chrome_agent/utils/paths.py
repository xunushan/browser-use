"""Utility functions for Chrome Agent."""

import os
import platform
from pathlib import Path


def get_runtime_dir() -> Path:
    """Get the runtime directory for Chrome Agent."""
    system = platform.system()
    if system == "Darwin":
        path = Path.home() / ".chrome-agent" / "run"
    elif system == "Linux":
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
        if xdg_runtime:
            path = Path(xdg_runtime) / "chrome-agent"
        else:
            path = Path.home() / ".local" / "run" / "chrome-agent"
    else:
        # Windows fallback (not supported in V1)
        path = Path.home() / ".chrome-agent" / "run"

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
        path = Path.home() / ".chrome-agent"

    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def get_log_dir() -> Path:
    """Get the log directory for Chrome Agent."""
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_dir.chmod(0o700)
    return log_dir


def get_socket_path() -> Path:
    """Get the Unix socket path for the daemon."""
    return get_runtime_dir() / "daemon.sock"


def get_lock_path() -> Path:
    """Get the lock file path for the daemon."""
    return get_runtime_dir() / "daemon.lock"


def get_pid_path() -> Path:
    """Get the PID file path for the daemon."""
    return get_runtime_dir() / "daemon.pid"
