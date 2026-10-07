"""Tests for Chrome Agent CLI."""

import os
import site
import subprocess
import sys


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

    def test_ensure_without_daemon(self, tmp_path):
        """Test ensure without daemon returns error.

        The runtime directory comes from `Path.home()`, so an empty HOME is a
        machine with no daemon. Running against the real HOME instead means
        stopping the user's daemon and deleting its socket — which is what this
        test used to do, killing a live session every time the suite ran.
        """
        home = tmp_path / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home)}
        env.pop("XDG_RUNTIME_DIR", None)
        # Dependencies are installed under the real HOME's user site-packages,
        # so the isolated HOME needs them on the path to get as far as the
        # daemon check rather than dying on an import.
        env["PYTHONPATH"] = os.pathsep.join(
            [site.getusersitepackages(), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)

        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "ensure"],
            capture_output=True,
            text=True,
            env=env,
        )
        # Should fail since daemon is not running
        assert result.returncode != 0
        assert "ModuleNotFoundError" not in result.stderr
        assert "not running" in (result.stdout + result.stderr)

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

    def test_snapshot_help_documents_the_element_limit(self):
        """The 500-element ceiling is raisable; long lists need it raised."""
        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "page", "snapshot", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--limit" in result.stdout
        assert "0 means no limit" in result.stdout

    def test_tabs_help(self):
        """Test tabs command help."""
        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "tabs", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "open" in result.stdout
        assert "claim" in result.stdout
        assert "activate" in result.stdout
