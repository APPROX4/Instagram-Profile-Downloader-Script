"""
Configuration and Credentials Manager for INTAJECTION.
Handles encrypted credential storage and application settings persistence.
"""

import os
import json
from pathlib import Path
from cryptography.fernet import Fernet


class ConfigManager:
    """Manages encrypted credentials and application settings."""

    CONFIG_DIR_NAME = "Intajection"
    CONFIG_FILE = "config.json"
    KEY_FILE = "secret.key"

    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / self.CONFIG_FILE
        self.key_path = self.config_dir / self.KEY_FILE
        self._cipher = self._get_cipher()

    # ── Directory ──────────────────────────────────────────────

    def _get_config_dir(self) -> Path:
        """Get the application data directory (%APPDATA%/Intajection)."""
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(appdata) / self.CONFIG_DIR_NAME

    # ── Encryption ─────────────────────────────────────────────

    def _get_cipher(self) -> Fernet:
        """Load or create a Fernet encryption key."""
        if self.key_path.exists():
            key = self.key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
        return Fernet(key)

    def _encrypt(self, text: str) -> str:
        return self._cipher.encrypt(text.encode()).decode()

    def _decrypt(self, token: str) -> str:
        return self._cipher.decrypt(token.encode()).decode()

    # ── Config I/O ─────────────────────────────────────────────

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                return {}
        return {}

    def _save_config(self, config: dict):
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # ── Credentials ────────────────────────────────────────────

    def save_credentials(self, username: str, password: str):
        """Encrypt and persist login credentials."""
        config = self._load_config()
        config["username"] = self._encrypt(username)
        config["password"] = self._encrypt(password)
        config["remember_me"] = True
        self._save_config(config)

    def load_credentials(self) -> tuple:
        """Return (username, password) or (None, None) if unavailable."""
        config = self._load_config()
        if config.get("remember_me") and config.get("username") and config.get("password"):
            try:
                return self._decrypt(config["username"]), self._decrypt(config["password"])
            except Exception:
                return None, None
        return None, None

    def clear_credentials(self):
        """Remove saved credentials."""
        config = self._load_config()
        config.pop("username", None)
        config.pop("password", None)
        config["remember_me"] = False
        self._save_config(config)

    # ── Settings ───────────────────────────────────────────────

    def get_download_order(self) -> str:
        """Return 'images_first' (default) or 'reels_first'."""
        return self._load_config().get("download_order", "images_first")

    def set_download_order(self, order: str):
        config = self._load_config()
        config["download_order"] = order
        self._save_config(config)

    def get_remember_me(self) -> bool:
        return self._load_config().get("remember_me", False)
