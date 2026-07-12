"""Vision Provider for Chrome Agent.

Provides integration with GLM-4.6V-Flash for visual analysis of screenshots.
"""

import base64
import hashlib
import json
import logging
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .config import ConfigManager

logger = logging.getLogger(__name__)


class VisionRequest:
    """Vision analysis request."""

    def __init__(self, image_path: str, task: str, purpose: str = "locate_element"):
        self.image_path = image_path
        self.task = task
        self.purpose = purpose


class VisionResult:
    """Vision analysis result."""

    def __init__(self, summary: str, candidates: list, model: str = "glm-4.6v-flash"):
        self.summary = summary
        self.candidates = candidates
        self.model = model


class VisionProvider(ABC):
    """Abstract base class for vision providers."""

    @abstractmethod
    def analyze(self, request: VisionRequest) -> VisionResult:
        """Analyze an image and return results."""
        pass


class GlmVisionProvider(VisionProvider):
    """GLM-4.6V-Flash vision provider."""

    def __init__(self, api_key: Optional[str] = None):
        if api_key:
            self.api_key = api_key
        else:
            # Use ConfigManager to get API key securely
            config = ConfigManager()
            self.api_key = config.get_api_key("glm")

    def analyze(self, request: VisionRequest) -> VisionResult:
        """Analyze an image using GLM-4.6V-Flash."""
        logger.info(f"Analyzing image with GLM-4.6V-Flash: {request.task}")

        # Read image and convert to base64
        with open(request.image_path, "rb") as f:
            image_data = f.read()

        image_base64 = base64.b64encode(image_data).decode("utf-8")

        # In a real implementation, this would call the GLM API
        # For now, return a mock result
        logger.info("Mock GLM analysis completed")

        return VisionResult(
            summary="Mock analysis result",
            candidates=[
                {
                    "label": "element",
                    "confidence": 0.95,
                    "point": {"x": 100, "y": 200},
                    "box": {"x": 50, "y": 150, "width": 100, "height": 50},
                }
            ],
            model="glm-4.6v-flash",
        )


class MockVisionProvider(VisionProvider):
    """Mock vision provider for testing."""

    def analyze(self, request: VisionRequest) -> VisionResult:
        """Return mock results."""
        return VisionResult(
            summary="Mock analysis result",
            candidates=[
                {
                    "label": "element",
                    "confidence": 0.95,
                    "point": {"x": 100, "y": 200},
                    "box": {"x": 50, "y": 150, "width": 100, "height": 50},
                }
            ],
            model="mock",
        )


class VisionService:
    """Vision service for managing screenshot analysis."""

    def __init__(self, provider: Optional[VisionProvider] = None):
        self.provider = provider or self._create_default_provider()
        self.cache = {}
        self.max_cache_size = 100

    def _create_default_provider(self) -> VisionProvider:
        """Create default vision provider."""
        try:
            return GlmVisionProvider()
        except ValueError:
            logger.warning("GLM API key not found, using mock provider")
            return MockVisionProvider()

    def analyze_screenshot(self, image_path: str, task: str, purpose: str = "locate_element") -> VisionResult:
        """Analyze a screenshot."""
        # Check cache
        cache_key = self._get_cache_key(image_path, task)
        if cache_key in self.cache:
            logger.info("Using cached vision result")
            return self.cache[cache_key]

        # Analyze image
        request = VisionRequest(image_path, task, purpose)
        result = self.provider.analyze(request)

        # Cache result
        self.cache[cache_key] = result
        self._cleanup_cache()

        return result

    def _get_cache_key(self, image_path: str, task: str) -> str:
        """Generate cache key for image and task."""
        # Hash image content
        with open(image_path, "rb") as f:
            image_hash = hashlib.sha256(f.read()).hexdigest()

        return f"{image_hash}:{task}"

    def _cleanup_cache(self):
        """Clean up cache if it exceeds max size."""
        if len(self.cache) > self.max_cache_size:
            # Remove oldest entries
            oldest_keys = list(self.cache.keys())[:len(self.cache) - self.max_cache_size]
            for key in oldest_keys:
                del self.cache[key]


class ScreenshotManager:
    """Manager for screenshot operations."""

    def __init__(self, temp_dir: Optional[Path] = None):
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "chrome-agent" / "screenshots"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts = {}

    def save_screenshot(self, data_url: str, tab_id: int) -> str:
        """Save screenshot from data URL to file."""
        # Extract base64 data from data URL
        if "," in data_url:
            _, base64_data = data_url.split(",", 1)
        else:
            base64_data = data_url

        # Decode base64
        image_data = base64.b64decode(base64_data)

        # Generate artifact ID
        artifact_id = f"img-{tab_id}-{int(time.time() * 1000)}"

        # Save to temp file
        image_path = self.temp_dir / f"{artifact_id}.png"
        with open(image_path, "wb") as f:
            f.write(image_data)

        # Store artifact info
        self.artifacts[artifact_id] = {
            "path": str(image_path),
            "tabId": tab_id,
            "createdAt": time.time(),
        }

        return artifact_id

    def get_screenshot_path(self, artifact_id: str) -> Optional[str]:
        """Get screenshot path by artifact ID."""
        artifact = self.artifacts.get(artifact_id)
        if artifact:
            return artifact["path"]
        return None

    def cleanup_old_screenshots(self, max_age: float = 900):
        """Clean up screenshots older than max_age seconds (default 15 minutes)."""
        current_time = time.time()
        to_remove = []

        for artifact_id, artifact in self.artifacts.items():
            if current_time - artifact["createdAt"] > max_age:
                # Delete file
                try:
                    Path(artifact["path"]).unlink()
                except FileNotFoundError:
                    pass
                to_remove.append(artifact_id)

        # Remove from tracking
        for artifact_id in to_remove:
            del self.artifacts[artifact_id]

    def cleanup_all(self):
        """Clean up all screenshots."""
        for artifact in self.artifacts.values():
            try:
                Path(artifact["path"]).unlink()
            except FileNotFoundError:
                pass

        self.artifacts.clear()
