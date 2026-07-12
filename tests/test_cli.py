"""Tests for Chrome Agent CLI."""

import subprocess
import sys
from pathlib import Path

import pytest


class TestCLI:
    """Test CLI commands."""

    def test_version_command(self):
        """Test version command returns version."""
        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Chrome Agent" in result.stdout

    def test_ensure_without_daemon(self):
        """Test ensure without daemon returns error."""
        # This test assumes no daemon is running
        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "ensure"],
            capture_output=True,
            text=True,
        )
        # Should fail since daemon is not running
        assert result.returncode != 0

    def test_cli_help(self):
        """Test CLI help shows available commands."""
        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "ensure" in result.stdout
        assert "start" in result.stdout
        assert "stop" in result.stdout
        assert "status" in result.stdout
        assert "version" in result.stdout
