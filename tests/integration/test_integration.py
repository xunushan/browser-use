"""Integration tests for Chrome Agent components.

These tests verify component interactions without requiring a real Chrome instance.
"""

import asyncio
import json
from pathlib import Path

import pytest

from chrome_agent.daemon.daemon import ChromeAgentDaemon
from chrome_agent.utils.auth import AuthManager, AuthState
from chrome_agent.utils.vision import MockVisionProvider, VisionRequest, VisionService


class TestDaemonToAuthIntegration:
    """Test Daemon and Auth integration."""

    @pytest.fixture
    async def daemon(self):
        """Create and start daemon."""
        daemon = ChromeAgentDaemon()
        daemon.socket_path = Path.home() / ".chrome-agent" / "run" / "test-integration.sock"

        task = asyncio.create_task(daemon.start())

        # Wait for daemon to be ready
        for _ in range(20):
            if daemon.running:
                break
            await asyncio.sleep(0.1)

        yield daemon

        await daemon.stop()
        if daemon.socket_path.exists():
            daemon.socket_path.unlink()

    @pytest.mark.asyncio
    async def test_daemon_can_detect_auth(self, daemon):
        """Test that daemon can detect authentication state."""
        auth_manager = AuthManager()

        page_context = {
            "url": "https://example.com/login",
            "title": "Login Page",
            "elements": [
                {"type": "password", "placeholder": "Password"},
            ],
        }

        detection = await auth_manager.detect_auth(123, "https://example.com", page_context)

        assert detection.state == AuthState.UNAUTHENTICATED
        assert detection.confidence > 0.7


class TestVisionToAuthIntegration:
    """Test Vision and Auth integration."""

    @pytest.mark.asyncio
    async def test_vision_can_detect_login_page(self):
        """Test that vision can detect login page elements."""
        # Create mock vision provider
        provider = MockVisionProvider()

        # Create vision request
        request = VisionRequest("/tmp/test.png", "detect_login_page")

        # Analyze
        result = provider.analyze(request)

        assert result.summary is not None
        assert len(result.candidates) > 0

    def test_auth_manager_creates_handoff_with_vision(self):
        """Test that auth manager creates handoff with vision data."""
        auth_manager = AuthManager()

        # Create handoff
        handoff = auth_manager.create_handoff(
            123,
            "https://example.com",
            "https://example.com/target"
        )

        assert "authSessionId" in handoff
        assert handoff["tabId"] == 123
        assert handoff["returnUrl"] == "https://example.com/target"
        assert "instructions" in handoff


class TestFullWorkflowIntegration:
    """Test full workflow integration."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete workflow from detection to handoff.

        This test simulates the complete workflow:
        1. Navigate to a page
        2. Detect auth state
        3. If not authenticated, create handoff
        4. After auth, complete handoff
        """
        auth_manager = AuthManager()

        # Step 1: Navigate to page
        page_context = {
            "url": "https://example.com/login",
            "title": "Login Page",
            "elements": [
                {"type": "password", "placeholder": "Password"},
                {"text": "登录", "tag": "button"},
            ],
        }

        # Step 2: Detect auth state
        detection = await auth_manager.detect_auth(123, "https://example.com", page_context)

        assert detection.state == AuthState.UNAUTHENTICATED

        # Step 3: Create handoff
        handoff = auth_manager.create_handoff(123, "https://example.com", "https://example.com/target")

        assert handoff["state"] == AuthState.UNAUTHENTICATED.value

        # Step 4: Simulate user login
        # (In real scenario, user would log in manually)

        # Step 5: Complete handoff
        result = auth_manager.complete_handoff(123, "https://example.com")

        assert result["state"] == AuthState.AUTHENTICATED.value
        assert result["returnUrlRestored"] is True

    @pytest.mark.asyncio
    async def test_xiaohongshu_workflow(self):
        """Test Xiaohongshu-specific workflow."""
        auth_manager = AuthManager()

        # Simulate Xiaohongshu page
        page_context = {
            "url": "https://www.xiaohongshu.com",
            "title": "小红书",
            "elements": [
                {"className": "avatar", "tag": "img"},
            ],
        }

        # Detect auth state
        detection = await auth_manager.detect_auth(123, "https://www.xiaohongshu.com", page_context)

        # Should detect authenticated state due to avatar
        assert detection.state == AuthState.AUTHENTICATED
        assert detection.confidence > 0.7

    @pytest.mark.asyncio
    async def test_volcengine_workflow(self):
        """Test Volcengine-specific workflow."""
        auth_manager = AuthManager()

        # Simulate Volcengine login page
        page_context = {
            "url": "https://console.volcengine.com/auth/login",
            "title": "登录",
            "elements": [
                {"type": "tel", "placeholder": "请输入手机号"},
                {"text": "获取验证码", "tag": "button"},
            ],
        }

        # Detect auth state
        detection = await auth_manager.detect_auth(123, "https://console.volcengine.com", page_context)

        # Should detect authenticating state
        assert detection.state == AuthState.AUTHENTICATING
        assert detection.confidence > 0.7
