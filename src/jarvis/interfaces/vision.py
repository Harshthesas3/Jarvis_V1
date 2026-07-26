"""Screen capture and vision analysis interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class ScreenCapture(ABC):
    """Screen capture interface."""

    @abstractmethod
    def capture(self, output_path: Optional[str] = None) -> Optional[str]:
        """Capture the screen. Returns path to the screenshot."""

    @abstractmethod
    def capture_region(self, x: int, y: int, width: int, height: int, output_path: Optional[str] = None) -> Optional[str]:
        """Capture a region of the screen."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if screen capture is available."""


class VisionAnalyzer(ABC):
    """Vision-based screen content analysis."""

    @abstractmethod
    def analyze(self, image_path: str, prompt: str) -> str:
        """Analyze a screenshot with a vision-language model."""

    @abstractmethod
    def describe(self, image_path: str) -> str:
        """Describe what's visible on screen."""

    @abstractmethod
    def analyze_error(self, image_path: str) -> str:
        """Analyze an error shown on the screen."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the vision model is available."""
