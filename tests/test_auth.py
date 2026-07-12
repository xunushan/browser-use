"""Tests for Authentication System."""

import pytest

from chrome_agent.utils.auth import (
    AuthAdapterRegistry,
    AuthDetection,
    AuthManager,
    AuthSession,
    AuthState,
    GenericAuthAdapter,
    VolcengineAuthAdapter,
    XiaohongshuAuthAdapter,
)


class TestAuthState:
    """Test authentication states."""

    def test_auth_states(self):
        """Test that all auth states are defined."""
        assert AuthState.UNKNOWN == "UNKNOWN"
        assert AuthState.AUTHENTICATED == "AUTHENTICATED"
        assert AuthState.UNAUTHENTICATED == "UNAUTHENTICATED"
        assert AuthState.AUTHENTICATING == "AUTHENTICATING"
        assert AuthState.CHALLENGE_REQUIRED == "CHALLENGE_REQUIRED"
        assert AuthState.SESSION_EXPIRED == "SESSION_EXPIRED"


class TestGenericAuthAdapter:
    """Test generic auth adapter."""

    @pytest.mark.asyncio
    async def test_generic_adapter_detects_login_page(self):
        """Test that generic adapter detects login page."""
        adapter = GenericAuthAdapter()
        page_context = {
            "url": "https://example.com/login",
            "title": "Login Page",
            "elements": [
                {"type": "password", "placeholder": "Password"},
            ],
        }

        result = await adapter.detect(page_context)

        assert result.state == AuthState.UNAUTHENTICATED
        assert result.confidence > 0.7
        assert len(result.evidence) > 0

    @pytest.mark.asyncio
    async def test_generic_adapter_detects_unknown_page(self):
        """Test that generic adapter handles unknown page."""
        adapter = GenericAuthAdapter()
        page_context = {
            "url": "https://example.com/home",
            "title": "Home Page",
            "elements": [],
        }

        result = await adapter.detect(page_context)

        assert result.state == AuthState.UNKNOWN
        assert result.confidence == 0.5


class TestXiaohongshuAuthAdapter:
    """Test Xiaohongshu auth adapter."""

    @pytest.mark.asyncio
    async def test_xiaohongshu_adapter_matches(self):
        """Test that Xiaohongshu adapter matches correct URLs."""
        adapter = XiaohongshuAuthAdapter()

        assert adapter.matches("https://www.xiaohongshu.com")
        assert adapter.matches("https://xhslink.com/abc123")
        assert not adapter.matches("https://example.com")

    @pytest.mark.asyncio
    async def test_xiaohongshu_adapter_detects_login(self):
        """Test that Xiaohongshu adapter detects login state."""
        adapter = XiaohongshuAuthAdapter()
        page_context = {
            "url": "https://www.xiaohongshu.com/login",
            "title": "登录",
            "elements": [
                {"text": "登录", "tag": "button"},
            ],
        }

        result = await adapter.detect(page_context)

        assert result.state == AuthState.UNAUTHENTICATED
        assert result.confidence > 0.7


class TestVolcengineAuthAdapter:
    """Test Volcengine auth adapter."""

    @pytest.mark.asyncio
    async def test_volcengine_adapter_matches(self):
        """Test that Volcengine adapter matches correct URLs."""
        adapter = VolcengineAuthAdapter()

        assert adapter.matches("https://console.volcengine.com")
        assert adapter.matches("https://volcengine.com")
        assert not adapter.matches("https://example.com")

    @pytest.mark.asyncio
    async def test_volcengine_adapter_detects_auth_page(self):
        """Test that Volcengine adapter detects auth page."""
        adapter = VolcengineAuthAdapter()
        page_context = {
            "url": "https://console.volcengine.com/auth/login",
            "title": "登录",
            "elements": [
                {"type": "tel", "placeholder": "请输入手机号"},
                {"text": "获取验证码", "tag": "button"},
            ],
        }

        result = await adapter.detect(page_context)

        assert result.state in [AuthState.UNAUTHENTICATED, AuthState.AUTHENTICATING]
        assert result.confidence > 0.7


class TestAuthAdapterRegistry:
    """Test auth adapter registry."""

    def test_registry_has_default_adapters(self):
        """Test that registry has default adapters."""
        registry = AuthAdapterRegistry()

        assert len(registry.adapters) > 0

    def test_registry_finds_adapter(self):
        """Test that registry finds correct adapter."""
        registry = AuthAdapterRegistry()

        adapter = registry.get_adapter("https://www.xiaohongshu.com")
        assert adapter is not None
        assert adapter.site_name == "xiaohongshu"

    def test_registry_returns_generic_for_unknown(self):
        """Test that registry returns generic adapter for unknown URLs."""
        registry = AuthAdapterRegistry()

        # Should return generic adapter (last in list)
        adapter = registry.get_adapter("https://unknown-site.com")
        assert adapter is not None
        assert adapter.site_name == "generic"


class TestAuthSession:
    """Test auth session."""

    def test_session_creation(self):
        """Test session creation."""
        session = AuthSession(123, "https://example.com")

        assert session.tab_id == 123
        assert session.origin == "https://example.com"
        assert session.state == AuthState.UNKNOWN
        assert not session.is_expired()

    def test_session_expiry(self):
        """Test session expiry."""
        session = AuthSession(123, "https://example.com")

        # Manually set expiry to past
        from datetime import datetime, timedelta
        session.expires_at = datetime.now() - timedelta(seconds=1)

        assert session.is_expired()


class TestAuthManager:
    """Test auth manager."""

    @pytest.mark.asyncio
    async def test_manager_detects_auth(self):
        """Test manager detects auth state."""
        manager = AuthManager()
        page_context = {
            "url": "https://example.com/login",
            "title": "Login",
            "elements": [
                {"type": "password", "placeholder": "Password"},
            ],
        }

        result = await manager.detect_auth(123, "https://example.com", page_context)

        assert result.state == AuthState.UNAUTHENTICATED
        assert result.confidence > 0.7

    def test_manager_creates_handoff(self):
        """Test manager creates handoff."""
        manager = AuthManager()

        handoff = manager.create_handoff(123, "https://example.com", "https://example.com/target")

        assert "authSessionId" in handoff
        assert handoff["tabId"] == 123
        assert handoff["returnUrl"] == "https://example.com/target"
        assert "instructions" in handoff

    def test_manager_completes_handoff(self):
        """Test manager completes handoff."""
        manager = AuthManager()

        # Create handoff first
        manager.create_handoff(123, "https://example.com", "https://example.com/target")

        # Complete handoff
        result = manager.complete_handoff(123, "https://example.com")

        assert result["state"] == AuthState.AUTHENTICATED.value
        assert result["returnUrlRestored"] is True
