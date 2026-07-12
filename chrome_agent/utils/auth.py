"""Authentication adapters for Chrome Agent.

Provides site-specific authentication detection and handling.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class AuthState(str, Enum):
    """Authentication states."""
    UNKNOWN = "UNKNOWN"
    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    AUTHENTICATING = "AUTHENTICATING"
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"


@dataclass
class AuthEvidence:
    """Evidence for authentication state."""
    type: str
    value: str
    weight: float = 1.0


@dataclass
class AuthDetection:
    """Authentication detection result."""
    state: AuthState
    confidence: float
    checked_at: datetime
    evidence: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class AuthAdapter(ABC):
    """Abstract base class for authentication adapters."""

    @property
    @abstractmethod
    def site_name(self) -> str:
        """Site name."""
        pass

    @property
    @abstractmethod
    def origins(self) -> list:
        """List of supported origins."""
        pass

    def matches(self, url: str) -> bool:
        """Check if this adapter matches the given URL."""
        return any(origin in url for origin in self.origins)

    @abstractmethod
    async def detect(self, page_context: dict) -> AuthDetection:
        """Detect authentication state from page context."""
        pass

    @abstractmethod
    async def get_login_url(self, current_url: str) -> Optional[str]:
        """Get login URL for this site."""
        pass

    @abstractmethod
    async def detect_completion(self, page_context: dict) -> AuthDetection:
        """Detect if authentication is complete."""
        pass


class GenericAuthAdapter(AuthAdapter):
    """Generic authentication adapter for common sites."""

    @property
    def site_name(self) -> str:
        return "generic"

    @property
    def origins(self) -> list:
        return ["*"]

    async def detect(self, page_context: dict) -> AuthDetection:
        """Generic authentication detection."""
        url = page_context.get("url", "")
        title = page_context.get("title", "").lower()
        elements = page_context.get("elements", [])

        evidence = []

        # Check for login indicators in URL
        if any(pattern in url.lower() for pattern in ["login", "signin", "auth"]):
            evidence.append(AuthEvidence("url", url, 0.9))

        # Check for login indicators in title
        if any(pattern in title for pattern in ["login", "sign in", "auth"]):
            evidence.append(AuthEvidence("title", title, 0.8))

        # Check for login form elements
        login_elements = [
            el for el in elements
            if el.get("type") in ["password", "tel"]
            or any(
                pattern in (el.get("placeholder") or "").lower()
                for pattern in ["password", "phone", "验证码"]
            )
        ]

        if login_elements:
            evidence.append(AuthEvidence("dom", "login-form-visible", 0.95))

        # Determine state
        if evidence:
            return AuthDetection(
                state=AuthState.UNAUTHENTICATED,
                confidence=min(0.98, 0.7 + len(evidence) * 0.1),
                checked_at=datetime.now(),
                evidence=evidence,
            )

        return AuthDetection(
            state=AuthState.UNKNOWN,
            confidence=0.5,
            checked_at=datetime.now(),
            evidence=[],
        )

    async def get_login_url(self, current_url: str) -> Optional[str]:
        """No specific login URL for generic adapter."""
        return None

    async def detect_completion(self, page_context: dict) -> AuthDetection:
        """Generic completion detection."""
        return AuthDetection(
            state=AuthState.UNKNOWN,
            confidence=0.5,
            checked_at=datetime.now(),
            evidence=[],
        )


class XiaohongshuAuthAdapter(AuthAdapter):
    """Xiaohongshu (Little Red Book) authentication adapter."""

    @property
    def site_name(self) -> str:
        return "xiaohongshu"

    @property
    def origins(self) -> list:
        return ["xiaohongshu.com", "xhslink.com"]

    async def detect(self, page_context: dict) -> AuthDetection:
        """Detect Xiaohongshu authentication state."""
        url = page_context.get("url", "")
        title = page_context.get("title", "").lower()
        elements = page_context.get("elements", [])

        evidence = []

        # Check for login page
        if "login" in url.lower() or "signin" in url.lower():
            evidence.append(AuthEvidence("url", url, 0.9))

        # Check for user avatar (indicates logged in)
        avatar_elements = [
            el for el in elements
            if el.get("className") and "avatar" in el.get("className", "").lower()
        ]
        if avatar_elements:
            evidence.append(AuthEvidence("dom", "user-avatar-found", 0.85))

        # Check for login button
        login_buttons = [
            el for el in elements
            if any(pattern in (el.get("text") or "").lower()
                  for pattern in ["登录", "login", "sign in"])
        ]
        if login_buttons:
            evidence.append(AuthEvidence("dom", "login-button-found", 0.9))

        # Determine state
        if avatar_elements and not login_buttons:
            return AuthDetection(
                state=AuthState.AUTHENTICATED,
                confidence=0.85,
                checked_at=datetime.now(),
                evidence=evidence,
            )
        elif login_buttons:
            return AuthDetection(
                state=AuthState.UNAUTHENTICATED,
                confidence=0.9,
                checked_at=datetime.now(),
                evidence=evidence,
            )

        return AuthDetection(
            state=AuthState.UNKNOWN,
            confidence=0.5,
            checked_at=datetime.now(),
            evidence=evidence,
        )

    async def get_login_url(self, current_url: str) -> Optional[str]:
        """Get Xiaohongshu login URL."""
        return "https://www.xiaohongshu.com/login"

    async def detect_completion(self, page_context: dict) -> AuthDetection:
        """Detect if Xiaohongshu login is complete."""
        return await self.detect(page_context)


class VolcengineAuthAdapter(AuthAdapter):
    """Volcengine (ByteDance Cloud) authentication adapter."""

    @property
    def site_name(self) -> str:
        return "volcengine"

    @property
    def origins(self) -> list:
        return ["volcengine.com", "console.volcengine.com"]

    async def detect(self, page_context: dict) -> AuthDetection:
        """Detect Volcengine authentication state."""
        url = page_context.get("url", "")
        title = page_context.get("title", "").lower()
        elements = page_context.get("elements", [])

        evidence = []

        # Check for login page
        if "/auth/" in url or "/login" in url:
            evidence.append(AuthEvidence("url", url, 0.95))

        # Check for phone input
        phone_inputs = [
            el for el in elements
            if el.get("type") == "tel" or
            any(pattern in (el.get("placeholder") or "").lower()
            for pattern in ["手机号", "phone"])
        ]
        if phone_inputs:
            evidence.append(AuthEvidence("dom", "phone-input-found", 0.9))

        # Check for verification code input
        code_inputs = [
            el for el in elements
            if any(pattern in (el.get("placeholder") or "").lower()
                  for pattern in ["验证码", "code", "verification"])
        ]
        if code_inputs:
            evidence.append(AuthEvidence("dom", "code-input-found", 0.85))

        # Check for user menu (indicates logged in)
        user_menus = [
            el for el in elements
            if el.get("text") and any(pattern in el.get("text", "").lower()
                                       for pattern in ["退出", "logout", "账户"])
        ]
        if user_menus:
            evidence.append(AuthEvidence("dom", "user-menu-found", 0.9))

        # Determine state
        if user_menus and not phone_inputs:
            return AuthDetection(
                state=AuthState.AUTHENTICATED,
                confidence=0.9,
                checked_at=datetime.now(),
                evidence=evidence,
            )
        elif phone_inputs or code_inputs:
            return AuthDetection(
                state=AuthState.AUTHENTICATING,
                confidence=0.9,
                checked_at=datetime.now(),
                evidence=evidence,
            )
        elif "/auth/" in url:
            return AuthDetection(
                state=AuthState.UNAUTHENTICATED,
                confidence=0.95,
                checked_at=datetime.now(),
                evidence=evidence,
            )

        return AuthDetection(
            state=AuthState.UNKNOWN,
            confidence=0.5,
            checked_at=datetime.now(),
            evidence=evidence,
        )

    async def get_login_url(self, current_url: str) -> Optional[str]:
        """Get Volcengine login URL."""
        return "https://console.volcengine.com/auth/login"

    async def detect_completion(self, page_context: dict) -> AuthDetection:
        """Detect if Volcengine login is complete."""
        return await self.detect(page_context)


class AuthAdapterRegistry:
    """Registry for authentication adapters."""

    def __init__(self):
        self.adapters: list[AuthAdapter] = []
        self._register_default_adapters()

    def _register_default_adapters(self):
        """Register default adapters."""
        self.register(XiaohongshuAuthAdapter())
        self.register(VolcengineAuthAdapter())
        self.register(GenericAuthAdapter())

    def register(self, adapter: AuthAdapter):
        """Register an adapter."""
        self.adapters.append(adapter)
        logger.info(f"Registered auth adapter: {adapter.site_name}")

    def get_adapter(self, url: str) -> Optional[AuthAdapter]:
        """Get adapter for URL."""
        for adapter in self.adapters:
            if adapter.matches(url):
                return adapter
        # Fallback to generic adapter (last in list)
        if self.adapters:
            return self.adapters[-1]
        return None

    async def detect_auth(self, url: str, page_context: dict) -> AuthDetection:
        """Detect authentication state for URL."""
        adapter = self.get_adapter(url)
        if adapter:
            return await adapter.detect(page_context)

        # Fallback to generic adapter
        generic = GenericAuthAdapter()
        return await generic.detect(page_context)


class AuthSession:
    """Authentication session tracking."""

    def __init__(self, tab_id: int, origin: str):
        self.tab_id = tab_id
        self.origin = origin
        self.state = AuthState.UNKNOWN
        self.confidence = 0.0
        self.checked_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(seconds=30)
        self.evidence = []
        self.auth_session_id = None
        self.return_url = None

    def is_expired(self) -> bool:
        """Check if session is expired."""
        return datetime.now() > self.expires_at

    def update(self, detection: AuthDetection):
        """Update session with new detection."""
        self.state = detection.state
        self.confidence = detection.confidence
        self.checked_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(seconds=30)
        self.evidence = detection.evidence


class AuthManager:
    """Manager for authentication sessions."""

    def __init__(self):
        self.sessions: dict[str, AuthSession] = {}
        self.registry = AuthAdapterRegistry()

    def get_session_key(self, tab_id: int, origin: str) -> str:
        """Generate session key."""
        return f"{tab_id}:{origin}"

    def get_session(self, tab_id: int, origin: str) -> Optional[AuthSession]:
        """Get or create session."""
        key = self.get_session_key(tab_id, origin)
        if key not in self.sessions:
            self.sessions[key] = AuthSession(tab_id, origin)
        return self.sessions[key]

    def clear_session(self, tab_id: int, origin: str):
        """Clear session."""
        key = self.get_session_key(tab_id, origin)
        if key in self.sessions:
            del self.sessions[key]

    async def detect_auth(self, tab_id: int, origin: str, page_context: dict) -> AuthDetection:
        """Detect authentication state."""
        session = self.get_session(tab_id, origin)

        # Check if cached session is still valid
        if not session.is_expired() and session.state != AuthState.UNKNOWN:
            return AuthDetection(
                state=session.state,
                confidence=session.confidence,
                checked_at=session.checked_at,
                evidence=session.evidence,
            )

        # Perform detection
        detection = await self.registry.detect_auth(origin, page_context)

        # Update session
        session.update(detection)

        return detection

    def create_handoff(self, tab_id: int, origin: str, return_url: str) -> dict:
        """Create authentication handoff."""
        session = self.get_session(tab_id, origin)
        session.auth_session_id = f"auth-{tab_id}-{int(datetime.now().timestamp())}"
        session.return_url = return_url

        return {
            "authSessionId": session.auth_session_id,
            "tabId": tab_id,
            "origin": origin,
            "returnUrl": return_url,
            "state": session.state.value,
            "instructions": "Please log in using the browser",
            "allowedActions": [
                "user_input_in_page",
                "secure_otp_input",
                "cancel",
            ],
            "expiresAt": (datetime.now() + timedelta(minutes=5)).isoformat(),
        }

    def complete_handoff(self, tab_id: int, origin: str) -> dict:
        """Complete authentication handoff."""
        session = self.get_session(tab_id, origin)
        session.state = AuthState.AUTHENTICATED
        session.confidence = 1.0

        return {
            "authSessionId": session.auth_session_id,
            "tabId": tab_id,
            "state": AuthState.AUTHENTICATED.value,
            "returnUrlRestored": True,
        }
