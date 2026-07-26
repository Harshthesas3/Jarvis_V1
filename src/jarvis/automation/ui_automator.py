"""UIAutomator — mouse and keyboard automation with safety bounds checking.

Provides a clean facade over PyAutoGUI and pywinauto for click, type, key,
scroll, and hotkey actions, all with coordinate validation and basic retry
semantics.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger("jarvis.automation.ui_automator")

# ---------------------------------------------------------------------------
# Screen bounds helpers
# ---------------------------------------------------------------------------
_screen_size: Optional[Tuple[int, int]] = None


def _get_screen_size() -> Tuple[int, int]:
    """Return the current screen (width, height)."""
    global _screen_size
    if _screen_size is None:
        try:
            import pyautogui

            w, h = pyautogui.size()
            _screen_size = (w, h)
        except Exception:
            _screen_size = (1920, 1080)  # fallback
    return _screen_size


def _clamp(x: Optional[int], y: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
    """Clamp coordinates to the current screen bounds.

    Returns ``(None, None)`` when either coordinate would be out of bounds
    and the caller can fall back to the current mouse position.
    """
    if x is None and y is None:
        return (None, None)
    w, h = _get_screen_size()
    cx = max(0, min(x, w - 1)) if x is not None else None
    cy = max(0, min(y, h - 1)) if y is not None else None
    return (cx, cy)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
def _retry(fn, max_attempts: int = 3, delay: float = 0.3, *args, **kwargs) -> bool:
    """Execute *fn* with up to *max_attempts* attempts."""
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn(*args, **kwargs)
            if result is not False and result is not None:
                return True
        except Exception as exc:
            logger.debug("Attempt %d/%d failed: %s", attempt, max_attempts, exc)
        if attempt < max_attempts:
            time.sleep(delay)
    return False


# ---------------------------------------------------------------------------
# UIAutomator
# ---------------------------------------------------------------------------
class UIAutomator:
    """Mouse and keyboard automation with safe coordinate bounds checking.

    All click / type / key operations leverage PyAutoGUI under the hood.
    Coordinates are clamped to the screen dimensions before being passed to
    the underlying library so that out-of-bounds coordinates never trigger
    unexpected behaviour.
    """

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------
    @staticmethod
    def click(
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
    ) -> bool:
        """Click at (*x*, *y*) with the given *button*.

        If both *x* and *y* are ``None`` the click happens at the current
        mouse position.
        """
        import pyautogui

        cx, cy = _clamp(x, y)
        return _retry(pyautogui.click, args=(cx, cy, button))

    @staticmethod
    def double_click(x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Double-click at (*x*, *y*)."""
        import pyautogui

        cx, cy = _clamp(x, y)
        return _retry(pyautogui.doubleClick, args=(cx, cy))

    @staticmethod
    def right_click(x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Right-click at (*x*, *y*)."""
        import pyautogui

        cx, cy = _clamp(x, y)
        return _retry(pyautogui.rightClick, args=(cx, cy))

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------
    @staticmethod
    def type_text(text: str) -> bool:
        """Type *text* into the currently focused element."""
        if not text:
            return True
        import pyautogui

        return _retry(pyautogui.typewrite, args=(text,), kwargs={"interval": 0.05})

    @staticmethod
    def press_key(key: str) -> bool:
        """Press a single *key* (e.g. ``"enter"``, ``"tab"``)."""
        if not key:
            return False
        import pyautogui

        return _retry(pyautogui.press, args=(key,))

    @staticmethod
    def hotkey(*keys: str) -> bool:
        """Press a combination of *keys* simultaneously.

        Example: ``hotkey("ctrl", "c")`` copies to clipboard.
        """
        if not keys:
            return False
        import pyautogui

        return _retry(pyautogui.hotkey, args=keys)

    # ------------------------------------------------------------------
    # Scroll
    # ------------------------------------------------------------------
    @staticmethod
    def scroll(
        direction: str = "down",
        amount: int = 3,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> bool:
        """Scroll by *amount* clicks in the given *direction*.

        Supported *direction* values: ``"down"``, ``"up"``, ``"left"``,
        ``"right"``.
        """
        import pyautogui

        clicks = -amount if direction in ("down", "right") else amount
        cx, cy = _clamp(x, y)
        return _retry(pyautogui.scroll, args=(clicks, cx, cy))
