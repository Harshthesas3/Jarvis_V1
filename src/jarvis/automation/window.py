"""WindowManager implementation using PyAutoGUI and Win32 APIs.

Implements the WindowManager interface from jarvis.interfaces.automation
by wrapping the existing low-level Win32 helpers in ``ui_core``.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from jarvis.interfaces.automation import WindowManager as WindowManagerInterface
from jarvis.types import WindowInfo

logger = logging.getLogger("jarvis.automation.window")


class WindowManager(WindowManagerInterface):
    """Manage desktop windows via Win32 API through PyAutoGUI and ctypes.

    Delegates to the ``WindowManager`` class defined in ``ui_core`` for
    the actual Win32 interaction while adapting the local ``WindowInfo``
    dataclass to the interface type from ``jarvis.types``.
    """

    def __init__(self) -> None:
        self._core = _get_core_wm()
        self._has_win32 = _check_win32()

    # ------------------------------------------------------------------
    # Interface: get_active_window
    # ------------------------------------------------------------------
    def get_active_window(self) -> Optional[WindowInfo]:
        """Get the currently focused foreground window."""
        if not self._has_win32:
            return None
        try:
            cw = self._core.get_active_window()
            if cw is None:
                return None
            return self._to_window_info(cw)
        except Exception:
            logger.exception("get_active_window failed")
            return None

    # ------------------------------------------------------------------
    # Interface: find_window
    # ------------------------------------------------------------------
    def find_window(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
    ) -> Optional[WindowInfo]:
        """Find the first visible window matching the given criteria."""
        if not self._has_win32:
            return None
        try:
            cw = self._core.find_window(
                title_pattern=title, class_name=class_name
            )
            if cw is None:
                return None
            return self._to_window_info(cw)
        except Exception:
            logger.exception("find_window failed")
            return None

    # ------------------------------------------------------------------
    # Interface: enum_windows
    # ------------------------------------------------------------------
    def enum_windows(self) -> List[WindowInfo]:
        """Enumerate all visible top-level windows."""
        if not self._has_win32:
            return []
        try:
            cw_list = self._core.find_windows()
            return [self._to_window_info(cw) for cw in cw_list]
        except Exception:
            logger.exception("enum_windows failed")
            return []

    def get_all_windows(self) -> List[WindowInfo]:
        """Alias for :meth:`enum_windows`."""
        return self.enum_windows()

    # ------------------------------------------------------------------
    # Interface: focus_window
    # ------------------------------------------------------------------
    def focus_window(self, hwnd: int) -> bool:
        """Bring the window identified by *hwnd* to the foreground."""
        if not self._has_win32:
            return False
        try:
            return self._core.focus_window(hwnd)
        except Exception:
            logger.exception("focus_window failed for hwnd %d", hwnd)
            return False

    def focus(self, title: str) -> bool:
        """Find a window by title and bring it to the foreground.

        Returns ``True`` if the window was found and focused.
        """
        cw = self._core.find_window(title_pattern=title)
        if cw is None:
            return False
        return self._core.focus_window(cw)

    # ------------------------------------------------------------------
    # Interface: wait_for_window
    # ------------------------------------------------------------------
    def wait_for_window(
        self, title: str, timeout: float = 15.0
    ) -> bool:
        """Wait for a window with a matching title to appear.

        Returns ``True`` if the window appeared within *timeout* seconds.
        """
        if not self._has_win32:
            return False
        try:
            cw = self._core.wait_for_window(
                title_pattern=title, timeout=timeout
            )
            return cw is not None
        except Exception:
            logger.exception("wait_for_window failed")
            return False

    # ------------------------------------------------------------------
    # Interface: is_valid_window
    # ------------------------------------------------------------------
    def is_valid_window(self, hwnd: int) -> bool:
        """Check whether a window handle is still valid.

        Uses ``IsWindow`` from the Win32 API.
        """
        if not self._has_win32:
            return False
        try:
            import ctypes

            return bool(ctypes.windll.user32.IsWindow(hwnd))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Convenience: switch_to
    # ------------------------------------------------------------------
    def switch_to(self, target: str) -> Optional[WindowInfo]:
        """Switch focus to the first window whose title contains *target*.

        Returns the ``WindowInfo`` of the focused window, or ``None`` if
        no matching window was found.
        """
        cw = self._core.find_window(title_pattern=target)
        if cw is None:
            return None
        ok = self._core.focus_window(cw.hwnd if hasattr(cw, "hwnd") else cw)
        if not ok:
            return None
        return self._to_window_info(cw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_window_info(cw) -> WindowInfo:
        """Convert a ``ui_core.WindowInfo`` to ``jarvis.types.WindowInfo``."""
        rect = getattr(cw, "rect", None)
        bounds = None
        if rect and len(rect) == 4:
            bounds = {
                "left": rect[0],
                "top": rect[1],
                "right": rect[2],
                "bottom": rect[3],
            }

        import psutil

        proc_name = "unknown"
        try:
            proc = psutil.Process(cw.process_id)
            proc_name = proc.name()
        except Exception:
            pass

        return WindowInfo(
            hwnd=cw.hwnd,
            title=cw.title,
            class_name=getattr(cw, "class_name", ""),
            process_id=cw.process_id,
            process_name=proc_name,
            bounds=bounds,
            is_visible=getattr(cw, "is_visible", True),
            is_focused=False,
        )


# ---------------------------------------------------------------------------
# Module-level helpers (lazy imports to avoid circular deps)
# ---------------------------------------------------------------------------
_core_wm_cache = None


def _get_core_wm():
    """Lazily import and return the ``ui_core.WindowManager`` class."""
    # ui_core.WindowManager is a class with static methods -- we instantiate
    # it once and reuse it so callers don't need to know.
    global _core_wm_cache
    if _core_wm_cache is not None:
        return _core_wm_cache
    try:
        import sys, os

        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
        )
        if root not in sys.path:
            sys.path.insert(0, root)

        # The module defines a class also called WindowManager.
        import importlib

        ui_core = importlib.import_module("ui_core")
        _core_wm_cache = ui_core.WindowManager()
    except ImportError:
        logger.warning("ui_core not available; WindowManager disabled")
        _core_wm_cache = None  # type: ignore[assignment]
    return _core_wm_cache


def _check_win32() -> bool:
    """Check whether the Win32 API is available."""
    try:
        import ctypes

        return hasattr(ctypes, "windll") and hasattr(
            ctypes.windll, "user32"
        )
    except Exception:
        return False
