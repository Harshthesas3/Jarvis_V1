"""Centralized logging configuration service."""

from __future__ import annotations

import logging
import sys
from typing import Optional


class LoggingService:
    """Configures consistent logging across all JARVIS modules."""

    def __init__(self, level: str = "INFO") -> None:
        self._level = level
        self._configured = False

    def configure(self, level: Optional[str] = None) -> None:
        if level:
            self._level = level

        logging.basicConfig(
            level=getattr(logging, self._level.upper(), logging.INFO),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stdout,
        )

        for name in ("httpx", "httpcore", "huggingface_hub", "faster_whisper",
                      "urllib3", "requests", "PIL", "onnxruntime"):
            logging.getLogger(name).setLevel(logging.ERROR)

        self._configured = True

    def get_logger(self, name: str) -> logging.Logger:
        if not self._configured:
            self.configure()
        return logging.getLogger(name)

    @staticmethod
    def suppress_loggers(names: list[str]) -> None:
        for name in names:
            logging.getLogger(name).setLevel(logging.ERROR)
