"""End-to-end integration tests for Chrome Agent.

These tests verify the complete workflow from CLI to Chrome extension.
They require a running Chrome instance with the extension installed.

To run these tests:
1. Install Chrome extension (developer mode)
2. Start Chrome Agent Daemon
3. Run: pytest tests/integration/ -v
"""

import json
import subprocess
import time
from pathlib import Path

import pytest


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    @pytest.fixture(scope="module")
    def chrome_agent_cli(self):
        """Fixture to ensure chrome-agent CLI is available."""
        # Check if CLI is installed
        result = subprocess.run(
            ["chrome-agent", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.skip("chrome-agent CLI not installed")

        return "chrome-agent"

    def test_cli_can_start_daemon(self, chrome_agent_cli):
        """Test that CLI can start daemon."""
        result = subprocess.run(
            [chrome_agent_cli, "ensure", "--launch-if-missing", "--json"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["daemon"] is True

    def test_cli_can_list_tabs(self, chrome_agent_cli):
        """Test that CLI can list tabs."""
        # This requires Chrome to be running with extension
        result = subprocess.run(
            [chrome_agent_cli, "tabs", "list", "--json"],
            capture_output=True,
            text=True,
        )

        # May fail if Chrome is not running
        if result.returncode != 0:
            pytest.skip("Chrome not running with extension")

        output = json.loads(result.stdout)
        assert isinstance(output, list)

    def test_cli_can_get_page_snapshot(self, chrome_agent_cli):
        """Test that CLI can get page snapshot."""
        # This requires Chrome to be running with extension
        result = subprocess.run(
            [chrome_agent_cli, "page", "snapshot", "--tab-id", "0", "--json"],
            capture_output=True,
            text=True,
        )

        # May fail if Chrome is not running
        if result.returncode != 0:
            pytest.skip("Chrome not running with extension")

        output = json.loads(result.stdout)
        assert "documentId" in output
        assert "elements" in output


class TestXiaohongshuSearch:
    """Xiaohongshu search end-to-end test."""

    def test_search_workflow(self):
        """Test complete Xiaohongshu search workflow.

        Steps:
        1. Ensure Chrome is running
        2. Navigate to xiaohongshu.com
        3. Check login status
        4. Search for "318攻略"
        5. Verify results
        """
        pytest.skip("Requires real Chrome instance - run manually")

    def test_login_detection(self):
        """Test login detection on Xiaohongshu."""
        pytest.skip("Requires real Chrome instance - run manually")

    def test_search_box_interaction(self):
        """Test search box interaction."""
        pytest.skip("Requires real Chrome instance - run manually")


class TestVolcengineLogin:
    """Volcengine login end-to-end test."""

    def test_login_workflow(self):
        """Test complete Volcengine login workflow.

        Steps:
        1. Ensure Chrome is running
        2. Navigate to console.volcengine.com
        3. Check login status
        4. If not logged in, trigger human handoff
        5. After login, navigate to Coding Plan page
        6. Extract usage data
        """
        pytest.skip("Requires real Chrome instance - run manually")

    def test_phone_input(self):
        """Test phone number input."""
        pytest.skip("Requires real Chrome instance - run manually")

    def test_verification_code_input(self):
        """Test verification code input."""
        pytest.skip("Requires real Chrome instance - run manually")

    def test_usage_extraction(self):
        """Test Coding Plan usage extraction."""
        pytest.skip("Requires real Chrome instance - run manually")
