"""Tests for Content Script and DOM Snapshot functionality."""

import json
from pathlib import Path


class TestContentScript:
    """Test Content Script functionality."""

    def test_content_script_exists(self):
        """Test that content script exists."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        assert script.exists()

    def test_content_script_has_required_functions(self):
        """Test that content script has required functions."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        # Check for required functions
        assert "buildSnapshot" in content
        assert "performClick" in content
        assert "performFill" in content
        assert "performScroll" in content
        assert "getElementRef" in content
        assert "getElementByRef" in content
        assert "collectImages" in content
        assert "loadAndCollectImages" in content
        assert "currentSrc" in content
        assert "srcset" in content
        assert "collectImages(root = document)" in content
        assert "Image scope element not found" in content
        assert "extractElementText" in content
        assert "returnedLength" in content
        assert "Text element not found" in content
        assert "collectMedia" in content
        assert "VideoObject" in content
        assert "urlType: 'blob'" in content

    def test_snapshot_preserves_complete_anchor_href(self):
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "element instanceof HTMLAnchorElement ? element.href" in content

    def test_scroll_supports_nested_scroll_containers(self):
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "findScrollTarget" in content
        assert "target.scrollBy" in content
        assert "moved:" in content

    def test_zero_size_overlay_links_use_visible_parent_rect(self):
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "getEffectiveRect" in content
        assert "const rect = getEffectiveRect(element);" in content
        assert "parentRect.width > 0" in content

    def test_content_script_has_document_id(self):
        """Test that content script generates document ID."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "DOCUMENT_ID" in content
        assert "documentId" in content

    def test_content_script_has_sensitive_data_handling(self):
        """Test that content script handles sensitive data."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "sensitive" in content.lower()
        assert "redacted" in content.lower()
        assert "password" in content.lower()

    def test_content_script_has_snapshot_scopes(self):
        """Test that content script supports different snapshot scopes."""
        script = Path(__file__).parent.parent / "extension" / "content.js"
        content = script.read_text()

        assert "viewport" in content
        assert "full" in content
        assert "element" in content


class TestBackgroundScript:
    """Test Background Script functionality."""

    def test_background_script_exists(self):
        """Test that background script exists."""
        script = Path(__file__).parent.parent / "extension" / "background.js"
        assert script.exists()

    def test_background_script_has_injection_functions(self):
        """Test that background script has injection functions."""
        script = Path(__file__).parent.parent / "extension" / "background.js"
        content = script.read_text()

        assert "injectContentScript" in content
        assert "registerContentScript" in content
        assert "unregisterContentScript" in content

    def test_background_script_has_reconnect_logic(self):
        """Test that background script has reconnect logic."""
        script = Path(__file__).parent.parent / "extension" / "background.js"
        content = script.read_text()

        assert "scheduleReconnect" in content
        assert "RECONNECT_DELAYS" in content
        assert "pageDownloadImages" in content
        assert "chrome.downloads.download" in content


class TestExtensionManifest:
    """Test Extension Manifest."""

    def test_manifest_has_required_permissions(self):
        """Test that manifest has required permissions."""
        manifest = Path(__file__).parent.parent / "extension" / "manifest.json"

        with open(manifest) as f:
            data = json.load(f)

        permissions = data["permissions"]
        assert "scripting" in permissions
        assert "storage" in permissions
        assert "tabs" in permissions
        assert "nativeMessaging" in permissions

    def test_manifest_has_optional_permissions(self):
        """Test that manifest has optional permissions."""
        manifest = Path(__file__).parent.parent / "extension" / "manifest.json"

        with open(manifest) as f:
            data = json.load(f)

        optional_permissions = data["optional_host_permissions"]
        assert "http://*/*" in optional_permissions
        assert "https://*/*" in optional_permissions

    def test_snapshot_element_limit_is_per_call_and_defaults_to_500(self):
        """The 500 ceiling is a real one: one dense list row is ~20 elements."""
        content = (Path(__file__).parent.parent / "extension" / "content.js").read_text()

        assert "const SNAPSHOT_DEFAULT_LIMIT = 500;" in content
        assert (
            "function buildSnapshot(scope = 'viewport', element = null, "
            "limit = SNAPSHOT_DEFAULT_LIMIT)" in content
        )
        # 0 means "no cap", so the caller can ask for the whole page.
        assert "const capped = limit > 0 ? elements.slice(0, limit) : elements;" in content
        assert "truncated: capped.length < elements.length," in content
        assert "params?.limit ?? SNAPSHOT_DEFAULT_LIMIT" in content

    def test_background_passes_the_snapshot_limit_through(self):
        background = (
            Path(__file__).parent.parent / "extension" / "background.js"
        ).read_text()

        assert "const { tabId, scope, limit } = params;" in background
        # Omitted means the content script's own default decides, so the number
        # lives in exactly one place.
        assert "limit === undefined ? { scope: scope || \"viewport\" }" in background
