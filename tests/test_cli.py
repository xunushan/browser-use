"""Tests for Chrome Agent CLI."""

import json
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
        assert "extension" in result.stdout

    def test_extension_help(self):
        """The group to check before sending anyone to chrome://extensions."""
        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "extension", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "status" in result.stdout
        assert "reload" in result.stdout

    def test_extension_status_and_reload_take_json(self):
        for command in ("status", "reload"):
            result = subprocess.run(
                [sys.executable, "-m", "chrome_agent.cli", "extension", command, "--help"],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, command
            assert "--json" in result.stdout, command

    def test_extension_status_answers_with_nothing_installed(self, tmp_path):
        """It answers when nothing is set up, which is when it is asked.

        A skill that is about to install has to be able to ask "is the extension
        already loaded?" on a machine with no daemon, no copy and no extension;
        failing there would push the caller back to telling the user to reload
        something they already have.
        """
        home = tmp_path / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home)}
        env.pop("XDG_RUNTIME_DIR", None)
        env["PYTHONPATH"] = os.pathsep.join(
            [site.getusersitepackages(), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)

        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "extension", "status", "--json"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, result.stderr
        status = json.loads(result.stdout)
        assert status["connected"] is False
        assert status["daemonRunning"] is False
        assert status["copied"] is False
        assert status["reloadNeeded"] is False

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

    def test_sites_help(self):
        """The two halves of the authorization story that are the CLI's.

        Granting needs a user gesture and stays in the popup, so it must not
        appear here as a command — a `grant` that cannot work is worse than no
        command at all.
        """
        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "sites", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "revoke" in result.stdout
        listed = result.stdout.split("Commands:", 1)[1].splitlines()
        assert not any(line.strip().startswith("grant") for line in listed)

    def test_sites_commands_take_json(self):
        for command in ("list", "revoke"):
            result = subprocess.run(
                [sys.executable, "-m", "chrome_agent.cli", "sites", command, "--help"],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, command
            assert "--json" in result.stdout, command

    def test_sites_help_points_granting_at_the_popup(self):
        """The agent must not go looking for a grant command that is not there."""
        result = subprocess.run(
            [sys.executable, "-m", "chrome_agent.cli", "sites", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "popup" in result.stdout

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


class TestLinuxChromeDiscovery:
    """Linux is supported but unverified here; the name matching is checkable.

    Distributions disagree on what the binary is called, so both the running
    check and the launch use the same list. This machine cannot run it, so what
    is asserted is the matching itself.
    """

    def test_the_usual_binary_names_are_covered(self):
        from chrome_agent.cli.main import LINUX_CHROME_BINARIES

        assert set(LINUX_CHROME_BINARIES) >= {
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        }

    def test_each_of_them_matches_a_process_command_line(self):
        import re

        from chrome_agent.cli.main import LINUX_CHROME_BINARIES, LINUX_CHROME_PATTERN

        for name in LINUX_CHROME_BINARIES:
            assert re.search(LINUX_CHROME_PATTERN, f"/usr/bin/{name} --flag"), name

    def test_a_name_that_merely_starts_alike_does_not_match(self):
        import re

        from chrome_agent.cli.main import LINUX_CHROME_PATTERN

        assert not re.search(LINUX_CHROME_PATTERN, "/usr/bin/chromium-helper --flag")
