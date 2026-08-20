"""Tests for DOM Operations (Issue #4)."""

from pathlib import Path


class TestDOMOperations:
    """Test DOM operation functionality."""

    def test_content_script_has_keypress_function(self):
        """Test that content script has keypress function."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "performKeypress" in content
        assert "KeyboardEvent" in content
        assert "keydown" in content
        assert "keyup" in content

    def test_content_script_has_wait_functions(self):
        """Test that content script has wait functions."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "waitForElement" in content
        assert "waitForUrlChange" in content
        assert "waitForMutation" in content
        assert "MutationObserver" in content

    def test_content_script_has_page_state_function(self):
        """Test that content script has page state function."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "getPageState" in content
        assert "readyState" in content

    def test_content_script_has_validate_function(self):
        """Test that content script has validate function."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "validateElement" in content
        assert "isConnected" in content

    def test_background_script_has_keypress_handler(self):
        """Test that background script has keypress handler."""
        script = Path(__file__).parent.parent / "extension" / "background.js"
        content = script.read_text()

        assert "pageKeypress" in content
        assert "pageWait" in content
        assert "pageValidate" in content

    def test_background_script_has_wait_handler(self):
        """Test that background script has wait handler."""
        script = Path(__file__).parent.parent / "extension" / "background.js"
        content = script.read_text()

        assert "page.wait" in content
        assert "page.validate" in content

    def test_keypress_event_types(self):
        """Test that keypress supports common keys."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        # Check for common keys
        assert "Enter" in content
        assert "Tab" in content
        assert "Escape" in content
        assert "ArrowUp" in content
        assert "ArrowDown" in content
        assert "Backspace" in content
        assert "Delete" in content
        assert "Space" in content

    def test_wait_conditions(self):
        """Test that wait supports different conditions."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "selector" in content
        assert "url" in content
        assert "mutation" in content

    def test_validate_checks(self):
        """Test that validate checks all conditions."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "Element not found" in content
        assert "Element no longer in DOM" in content
        assert "Element not visible" in content
        assert "Element is disabled" in content
