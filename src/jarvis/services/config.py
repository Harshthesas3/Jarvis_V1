"""Configuration service for JARVIS.

Thread-safe config manager with dot-notation access,
deep merge over defaults, and live reload support.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.services.config")

_DEFAULT_CONFIG: Dict[str, Any] = {
    "paths": {
        "piper_exe": "piper.exe",
        "voice_model": "voice.onnx",
        "screenshot_dir": "Screenshots",
    },
    "models": {
        "chat_model": "qwen3.5:4b",
        "planner_model": "qwen3.5:4b",
        "vision_model": "qwen2.5vl:3b",
    },
    "voice": {
        "wake_phrases": ["i'm back"],
        "chat_history_limit": 10,
    },
    "system": {
        "system_prompt": "You are JARVIS, a helpful AI assistant.",
    },
}


class ConfigService:
    """Thread-safe configuration with dot-notation access."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or os.environ.get("JARVIS_CONFIG", "config.json")
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self._data = dict(_DEFAULT_CONFIG)
            if os.path.exists(self._path):
                try:
                    with open(self._path, "r", encoding="utf-8") as f:
                        user_config = json.load(f)
                    self._data = self._deep_merge(self._data, user_config)
                except Exception as exc:
                    logger.warning("Failed to load config: %s", exc)

    def get(self, key_path: str, default: Any = None) -> Any:
        with self._lock:
            keys = key_path.split(".")
            val = self._data
            try:
                for k in keys:
                    val = val[k]
                return val
            except (KeyError, TypeError):
                return default

    def set(self, key_path: str, value: Any) -> None:
        with self._lock:
            keys = key_path.split(".")
            target = self._data
            for k in keys[:-1]:
                target = target.setdefault(k, {})
            target[keys[-1]] = value

    def save(self) -> bool:
        try:
            with self._lock:
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
            return True
        except Exception as exc:
            logger.error("Failed to save config: %s", exc)
            return False

    def all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and k in result and isinstance(result[k], dict):
                result[k] = ConfigService._deep_merge(result[k], v)
            else:
                result[k] = v
        return result
