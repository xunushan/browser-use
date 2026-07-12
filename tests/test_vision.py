"""Tests for Vision Provider and Screenshot Manager."""

import base64
import tempfile
from pathlib import Path

import pytest

from chrome_agent.utils.vision import (
    GlmVisionProvider,
    MockVisionProvider,
    ScreenshotManager,
    VisionRequest,
    VisionService,
)


class TestMockVisionProvider:
    """Test Mock Vision Provider."""

    def test_mock_provider_returns_result(self):
        """Test that mock provider returns a result."""
        provider = MockVisionProvider()
        request = VisionRequest("/tmp/test.png", "locate_element")

        result = provider.analyze(request)

        assert result.summary is not None
        assert len(result.candidates) > 0
        assert result.model == "mock"

    def test_mock_provider_returns_candidates(self):
        """Test that mock provider returns candidates."""
        provider = MockVisionProvider()
        request = VisionRequest("/tmp/test.png", "locate_element")

        result = provider.analyze(request)

        assert len(result.candidates) > 0
        candidate = result.candidates[0]
        assert "label" in candidate
        assert "confidence" in candidate
        assert "point" in candidate
        assert "box" in candidate


class TestGlmVisionProvider:
    """Test GLM Vision Provider."""

    def test_glm_provider_requires_api_key(self):
        """Test that GLM provider requires API key."""
        import os

        # Save original key
        original_key = os.environ.get("GLM_API_KEY")

        try:
            # Remove key
            if "GLM_API_KEY" in os.environ:
                del os.environ["GLM_API_KEY"]

            with pytest.raises(ValueError, match="GLM API key not found"):
                GlmVisionProvider()
        finally:
            # Restore key
            if original_key:
                os.environ["GLM_API_KEY"] = original_key

    def test_glm_provider_with_key(self):
        """Test that GLM provider works with key."""
        provider = GlmVisionProvider(api_key="test-key")
        assert provider.api_key == "test-key"


class TestVisionService:
    """Test Vision Service."""

    def test_vision_service_with_mock_provider(self):
        """Test vision service with mock provider."""
        service = VisionService(provider=MockVisionProvider())

        # Create a temporary image file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            # Write minimal PNG header
            f.write(b"\x89PNG\r\n\x1a\n")
            temp_path = f.name

        try:
            result = service.analyze_screenshot(temp_path, "locate_element")
            assert result.summary is not None
            assert len(result.candidates) > 0
        finally:
            Path(temp_path).unlink()

    def test_vision_service_caches_results(self):
        """Test that vision service caches results."""
        service = VisionService(provider=MockVisionProvider())

        # Create a temporary image file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n")
            temp_path = f.name

        try:
            # First call
            result1 = service.analyze_screenshot(temp_path, "locate_element")

            # Second call should use cache
            result2 = service.analyze_screenshot(temp_path, "locate_element")

            assert result1.summary == result2.summary
        finally:
            Path(temp_path).unlink()


class TestScreenshotManager:
    """Test Screenshot Manager."""

    def test_screenshot_manager_creates_temp_dir(self):
        """Test that screenshot manager creates temp directory."""
        manager = ScreenshotManager()
        assert manager.temp_dir.exists()

    def test_save_screenshot(self):
        """Test saving a screenshot."""
        manager = ScreenshotManager()

        # Create a simple base64 image
        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        data_url = f"data:image/png;base64,{base64.b64encode(image_data).decode()}"

        artifact_id = manager.save_screenshot(data_url, 123)

        assert artifact_id is not None
        assert artifact_id.startswith("img-")
        assert artifact_id in manager.artifacts

    def test_get_screenshot_path(self):
        """Test getting screenshot path."""
        manager = ScreenshotManager()

        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        data_url = f"data:image/png;base64,{base64.b64encode(image_data).decode()}"

        artifact_id = manager.save_screenshot(data_url, 123)
        path = manager.get_screenshot_path(artifact_id)

        assert path is not None
        assert Path(path).exists()

    def test_cleanup_old_screenshots(self):
        """Test cleaning up old screenshots."""
        manager = ScreenshotManager()

        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        data_url = f"data:image/png;base64,{base64.b64encode(image_data).decode()}"

        artifact_id = manager.save_screenshot(data_url, 123)

        # Manually set createdAt to old time
        manager.artifacts[artifact_id]["createdAt"] = 0

        # Cleanup old screenshots
        manager.cleanup_old_screenshots(max_age=1)

        # Should be removed
        assert artifact_id not in manager.artifacts

    def test_cleanup_all(self):
        """Test cleaning up all screenshots."""
        manager = ScreenshotManager()

        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        data_url = f"data:image/png;base64,{base64.b64encode(image_data).decode()}"

        manager.save_screenshot(data_url, 123)
        manager.save_screenshot(data_url, 456)

        # Cleanup all
        manager.cleanup_all()

        assert len(manager.artifacts) == 0
