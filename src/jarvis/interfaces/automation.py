"""Desktop automation interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from jarvis.types import ElementInfo, WindowInfo


class WindowManager(ABC):
    """Window enumeration, focus, and lifecycle management."""

    @abstractmethod
    def get_active_window(self) -> Optional[WindowInfo]:
        """Get the currently focused window."""

    @abstractmethod
    def find_window(self, title: Optional[str] = None, class_name: Optional[str] = None) -> Optional[WindowInfo]:
        """Find a window by title pattern or class name."""

    @abstractmethod
    def enum_windows(self) -> List[WindowInfo]:
        """Enumerate all visible top-level windows."""

    @abstractmethod
    def focus_window(self, hwnd: int) -> bool:
        """Bring a window to the foreground."""

    @abstractmethod
    def wait_for_window(self, title: str, timeout: float = 15.0) -> bool:
        """Wait for a window to appear."""

    @abstractmethod
    def is_valid_window(self, hwnd: int) -> bool:
        """Check if a window handle is still valid."""


class UIElement(ABC):
    """UI element interaction interface."""

    @abstractmethod
    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> bool:
        """Click at coordinates or on element."""

    @abstractmethod
    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Double-click at coordinates."""

    @abstractmethod
    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Right-click at coordinates."""

    @abstractmethod
    def type_text(self, text: str) -> bool:
        """Type text into the focused element."""

    @abstractmethod
    def press_key(self, key: str) -> bool:
        """Press a single key."""

    @abstractmethod
    def hotkey(self, *keys: str) -> bool:
        """Press a key combination."""

    @abstractmethod
    def scroll(self, direction: str = "down", amount: int = 3) -> bool:
        """Scroll in a direction."""

    @abstractmethod
    def move_mouse(self, x: int, y: int) -> bool:
        """Move mouse to absolute coordinates."""


class AppLauncher(ABC):
    """Application launch and verification."""

    @abstractmethod
    def launch(self, app_name: str) -> bool:
        """Launch an application by name or path."""

    @abstractmethod
    def launch_and_verify(self, app_name: str, wait_for_ui: bool = False) -> bool:
        """Launch an app and verify it started."""

    @abstractmethod
    def find_installed_apps(self) -> List[dict]:
        """Discover installed applications."""

    @abstractmethod
    def close_app(self, app_name: str) -> bool:
        """Close an application by process name."""


class SearchInApp(ABC):
    """In-application text search with prioritized fallbacks."""

    @abstractmethod
    def search(self, query: str, app: str, hwnd: int) -> dict:
        """Search for text in the given app window."""
