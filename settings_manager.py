import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger("jarvis.config")

class SettingsManager:
    """
    Handles loading and managing system configurations.
    Provides defaults if the config file is missing or corrupted.
    Thread-safe for concurrent access.
    """
    CONFIG_FILE = "config.json"

    def __init__(self):
        self._lock = threading.Lock()
        self._settings = self._load_defaults()
        self.reload()

    def _load_defaults(self) -> dict:
        return {
            "paths": {
                "piper_exe": "piper.exe",
                "voice_model": "voice.onnx",
                "screenshot_dir": "Screenshots"
            },
            "models": {
                "chat_model": "qwen3.5:4b",
                "planner_model": "qwen3.5:4b",
                "vision_model": "qwen2.5vl:3b"
            },
            "voice": {
                "wake_phrases": ["i'm back"],
                "chat_history_limit": 10
            },
            "system": {
                "system_prompt": "You are JARVIS."
            }
        }

    def reload(self) -> None:
        """Reload settings from disk. Thread-safe."""
        if not os.path.exists(self.CONFIG_FILE):
            logger.warning(f"Config file {self.CONFIG_FILE} not found. Using defaults.")
            return

        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                user_settings = json.load(f)
                with self._lock:
                    # Reset to defaults before merging to ensure a clean state on reload
                    base = self._load_defaults()
                    self._deep_update(base, user_settings)
                    self._settings = base
                logger.info("Configuration loaded successfully.")
        except Exception as exc:
            logger.error(f"Failed to load config: {exc}. Falling back to defaults.")

    def _deep_update(self, base: dict, update: dict) -> None:
        for k, v in update.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Retrieve a setting using dot notation (e.g., 'paths.piper_exe').
        Thread-safe.
        """
        with self._lock:
            keys = key_path.split(".")
            val = self._settings
            try:
                for k in keys:
                    val = val[k]
                return val
            except (KeyError, TypeError):
                return default

settings = SettingsManager()
