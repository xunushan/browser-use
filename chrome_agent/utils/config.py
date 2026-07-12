"""Configuration management for Chrome Agent.

Handles API keys and other sensitive configuration securely.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages Chrome Agent configuration."""

    def __init__(self):
        self.config_dir = Path.home() / ".chrome-agent"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.chmod(0o700)

    def get_api_key(self, provider: str = "glm") -> str:
        """Get API key for a provider.

        Priority:
        1. Environment variable
        2. System keychain/credential store
        3. Secure config file

        Args:
            provider: Provider name (e.g., "glm")

        Returns:
            API key string

        Raises:
            ValueError: If API key not found
        """
        env_var = f"{provider.upper()}_API_KEY"

        # 1. Check environment variable
        api_key = os.environ.get(env_var)
        if api_key:
            logger.debug(f"Found {provider} API key in environment variable")
            return api_key

        # 2. Check system keychain
        api_key = self._get_from_keychain(provider)
        if api_key:
            logger.debug(f"Found {provider} API key in system keychain")
            return api_key

        # 3. Check secure config file
        api_key = self._get_from_config_file(provider)
        if api_key:
            logger.debug(f"Found {provider} API key in config file")
            return api_key

        raise ValueError(
            f"{provider} API key not found. "
            f"Set {env_var} environment variable, "
            f"or use 'chrome-agent config set {provider}_api_key <key>'"
        )

    def set_api_key(self, provider: str, api_key: str) -> None:
        """Store API key securely.

        Stores in system keychain if available, otherwise in secure config file.

        Args:
            provider: Provider name (e.g., "glm")
            api_key: API key to store
        """
        # Try to store in system keychain
        if self._store_in_keychain(provider, api_key):
            logger.info(f"Stored {provider} API key in system keychain")
            return

        # Fallback to secure config file
        self._store_in_config_file(provider, api_key)
        logger.info(f"Stored {provider} API key in secure config file")

    def _get_from_keychain(self, provider: str) -> str:
        """Get API key from system keychain.

        Supports:
        - macOS: Keychain
        - Linux: Secret Service (libsecret)
        - Windows: Credential Manager
        """
        service_name = f"chrome-agent-{provider}"

        # macOS Keychain
        if sys.platform == "darwin":
            return self._get_from_macos_keychain(service_name)

        # Linux Secret Service
        if sys.platform == "linux":
            return self._get_from_linux_secret(service_name)

        # Windows Credential Manager
        if sys.platform == "win32":
            return self._get_from_windows_credential(service_name)

        return None

    def _store_in_keychain(self, provider: str, api_key: str) -> bool:
        """Store API key in system keychain.

        Returns:
            True if successful, False otherwise
        """
        service_name = f"chrome-agent-{provider}"

        # macOS Keychain
        if sys.platform == "darwin":
            return self._store_in_macos_keychain(service_name, api_key)

        # Linux Secret Service
        if sys.platform == "linux":
            return self._store_in_linux_secret(service_name, api_key)

        # Windows Credential Manager
        if sys.platform == "win32":
            return self._store_in_windows_credential(service_name, api_key)

        return False

    def _get_from_macos_keychain(self, service_name: str) -> str:
        """Get password from macOS Keychain."""
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service_name, "-w"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            pass
        return None

    def _store_in_macos_keychain(self, service_name: str, password: str) -> bool:
        """Store password in macOS Keychain."""
        try:
            import subprocess
            result = subprocess.run(
                ["security", "add-generic-password", "-s", service_name, "-w", password],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _get_from_linux_secret(self, service_name: str) -> str:
        """Get password from Linux Secret Service."""
        try:
            import secretstorage
            connection = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(connection)
            for item in collection.get_all_items():
                if item.get_label() == service_name:
                    return item.get_secret().decode("utf-8")
        except ImportError:
            pass
        except Exception:
            pass
        return None

    def _store_in_linux_secret(self, service_name: str, password: str) -> bool:
        """Store password in Linux Secret Service."""
        try:
            import secretstorage
            connection = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(connection)
            collection.create_item(service_name, {"service": service_name}, password.encode())
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def _get_from_windows_credential(self, service_name: str) -> str:
        """Get password from Windows Credential Manager."""
        try:
            import win32cred
            creds = win32cred.CredRead(service_name, win32cred.CRED_TYPE_GENERIC, 0)
            return creds["CredentialBlob"].decode("utf-16")
        except ImportError:
            pass
        except Exception:
            pass
        return None

    def _store_in_windows_credential(self, service_name: str, password: str) -> bool:
        """Store password in Windows Credential Manager."""
        try:
            import win32cred
            cred = {
                "Type": win32cred.CRED_TYPE_GENERIC,
                "TargetName": service_name,
                "CredentialBlob": password.encode("utf-16"),
                "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
            }
            win32cred.CredWrite(cred, 0)
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def _get_from_config_file(self, provider: str) -> str:
        """Get API key from secure config file."""
        config_file = self.config_dir / "secrets.json"
        if not config_file.exists():
            return None

        try:
            with open(config_file, "r") as f:
                config = json.load(f)
            return config.get(f"{provider}_api_key")
        except (json.JSONDecodeError, IOError):
            return None

    def _store_in_config_file(self, provider: str, api_key: str) -> None:
        """Store API key in secure config file.

        File permissions: 0600 (owner read/write only)
        """
        config_file = self.config_dir / "secrets.json"

        # Load existing config
        config = {}
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        # Update config
        config[f"{provider}_api_key"] = api_key

        # Write config
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Set secure permissions
        config_file.chmod(0o600)


import sys
