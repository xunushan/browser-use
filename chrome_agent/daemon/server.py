"""Server entry point for Chrome Agent Daemon."""

import asyncio
import logging
import sys

from ..utils.paths import get_log_dir


def setup_logging() -> None:
    """Set up logging for the daemon."""
    log_dir = get_log_dir()
    log_file = log_dir / "daemon.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(str(log_file)),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    """Main entry point for the daemon."""
    setup_logging()
    from .daemon import run_daemon
    asyncio.run(run_daemon())


if __name__ == "__main__":
    main()
