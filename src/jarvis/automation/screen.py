"""ScreenCapture implementation using mss for fast screenshots.

Implements the ScreenCapture interface from jarvis.interfaces.vision.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from jarvis.interfaces.vision import ScreenCapture as ScreenCaptureInterface

logger = logging.getLogger("jarvis.automation.screen")


class ScreenCapture(ScreenCaptureInterface):
    """Capture the screen or a region using ``mss`` (Multi-Screen
    Screenshot).

    Screenshots are saved as PNG files.  When no ``output_path`` is given
    a temporary file is created.
    """

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._mss = None

    # ------------------------------------------------------------------
    # Interface: capture
    # ------------------------------------------------------------------
    def capture(self, output_path: Optional[str] = None) -> Optional[str]:
        """Capture the entire screen.

        Returns the path to the saved PNG, or ``None`` on failure.
        """
        if not self.is_available():
            logger.error("Screen capture is not available")
            return None

        path = output_path or self._temp_path("fullscreen")
        try:
            sct = self._get_sct()
            # ``mss`` monitor 0 captures the full virtual screen (all monitors).
            sct_img = sct.grab(sct.monitors[0])
            self._save(sct_img, path)
            logger.info("Full screen capture saved to %s", path)
            return path
        except Exception:
            logger.exception("Full screen capture failed")
            return None

    # ------------------------------------------------------------------
    # Interface: capture_region
    # ------------------------------------------------------------------
    def capture_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """Capture a rectangular region of the screen.

        All parameters are in absolute screen coordinates.
        Returns the path to the saved PNG, or ``None`` on failure.
        """
        if not self.is_available():
            logger.error("Screen capture is not available")
            return None

        path = output_path or self._temp_path("region")
        try:
            sct = self._get_sct()
            monitor = {"left": x, "top": y, "width": width, "height": height}
            sct_img = sct.grab(monitor)
            self._save(sct_img, path)
            logger.info("Region capture [%d,%d %dx%d] saved to %s", x, y, width, height, path)
            return path
        except Exception:
            logger.exception("Region capture failed")
            return None

    # ------------------------------------------------------------------
    # Interface: is_available
    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        """Return ``True`` if ``mss`` is installed and importable."""
        if self._available is not None:
            return self._available
        try:
            import mss  # noqa: F401

            self._available = True
        except ImportError:
            logger.warning("mss is not installed; screen capture unavailable")
            self._available = False
        return self._available

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_sct(self):
        """Return a lazily-created ``mss.mss`` instance."""
        if self._mss is None:
            import mss

            self._mss = mss.mss()
        return self._mss

    @staticmethod
    def _save(sct_img, path: str) -> None:
        """Write an mss screenshot to *path* as PNG."""
        from PIL import Image

        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        img.save(path, format="PNG")

    @staticmethod
    def _temp_path(prefix: str) -> str:
        """Create a temporary file path for a screenshot."""
        fd, path = tempfile.mkstemp(suffix=".png", prefix=f"jarvis_{prefix}_")
        os.close(fd)
        return path
