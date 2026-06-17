"""
ui_core.py
----------
UI Automation subsystem for JARVIS with strict window validation.

Integrates PyAutoGUI, pywinauto, and Win32 APIs for:
  - Window detection, focus, and tracking with validation
  - Accessibility-based element location
  - Image-based fallback targeting
  - Safe click/type/scroll with retry and pre-flight checks
  - Session-aware context (current_window, current_app)
  - Strict window validation to prevent false matches

Public API:
    UIAutomator           — top-level facade
    WindowManager         — Win32 window enumeration / focus / wait
    ElementLocator        — find UI elements (accessibility + image)
    StrictWindowValidator — validates windows belong to requested apps
    session               — dict with current_window, current_app
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Dict, Tuple

logger = logging.getLogger("jarvis.ui")

# ---------------------------------------------------------------------------
# Session state (importable singleton)
# ---------------------------------------------------------------------------
session: dict[str, str] = {
    "current_window": "",
    "current_app": "",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    process_id: int
    rect: tuple[int, int, int, int]  # (left, top, right, bottom)
    is_visible: bool = True

    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]


@dataclass
class ElementInfo:
    control_type: str
    automation_id: str
    class_name: str
    name: str
    rect: tuple[int, int, int, int] | None = None
    is_enabled: bool = True

    @property
    def center(self) -> tuple[int, int]:
        if self.rect:
            cx = (self.rect[0] + self.rect[2]) // 2
            cy = (self.rect[1] + self.rect[3]) // 2
            return (cx, cy)
        return (0, 0)


# ---------------------------------------------------------------------------
# Known application profiles (validated, specific)
# ---------------------------------------------------------------------------
SUPPORTED_APPS: dict[str, dict[str, Any]] = {
    # Media Applications
    "apple music": {
        "class_names": ["WinUIDesktopBox"],
        "process_names": ["AppleMusic.exe", "Music.UI.exe"],
        "exact_title": "Apple Music",
        "title_patterns": ["Apple Music -", "Apple Music Preview"],
        "search_shortcut": ["ctrl", "f"],
    },
    "spotify": {
        "class_names": ["SpotifyMainWindow", "Chrome_WidgetWin_1"],
        "process_names": ["Spotify.exe"],
        "title_patterns": ["Spotify", "Spotify Premium"],
        "search_shortcut": ["ctrl", "l"],
    },
    
    # Browsers
    "brave": {
        "class_names": ["Chrome_WidgetWin_1"],
        "process_names": ["brave.exe"],
        "title_patterns": ["Brave"],
        "search_shortcut": ["ctrl", "l"],
    },
    "chrome": {
        "class_names": ["Chrome_WidgetWin_1", "Chrome_WidgetWin_0"],
        "process_names": ["chrome.exe"],
        "title_patterns": ["Google Chrome", "Chrome"],
        "search_shortcut": ["ctrl", "l"],
    },
    "microsoft edge": {
        "class_names": ["Edge_WidgetWin_0", "Edge_WidgetWin_1"],
        "process_names": ["msedge.exe"],
        "title_patterns": ["Microsoft Edge", "Edge"],
        "search_shortcut": ["ctrl", "l"],
    },
    "firefox": {
        "class_names": ["MozillaWindowClass", "FirefoxWindow"],
        "process_names": ["firefox.exe"],
        "title_patterns": ["Firefox", "Mozilla Firefox"],
        "search_shortcut": ["ctrl", "k"],
    },
    
    # IDEs / Code Editors
    "vs code": {
        "class_names": ["Chrome_WidgetWin_1"],
        "process_names": ["Code.exe"],
        "title_patterns": ["Visual Studio Code", "VS Code"],
        "search_shortcut": ["ctrl", "p"],
    },
    "visual studio code": {
        "class_names": ["Chrome_WidgetWin_1"],
        "process_names": ["Code.exe"],
        "title_patterns": ["Visual Studio Code", "VS Code"],
        "search_shortcut": ["ctrl", "p"],
    },
    
    # Microsoft Store Apps
    "microsoft store": {
        "class_names": ["Windows.UI.Core.CoreWindow"],
        "process_names": ["WinStore.App.exe"],
        "exact_title": "Microsoft Store",
        "title_patterns": ["Microsoft Store", "Store"],
        "search_shortcut": ["ctrl", "f"],
    },
    
    # File Management
    "file explorer": {
        "class_names": ["CabinetWClass"],
        "process_names": ["explorer.exe"],
        "title_patterns": ["File Explorer", "This PC", "Documents", "Downloads"],
        "search_shortcut": ["ctrl", "e"],
    },
    
    # Communication
    "slack": {
        "class_names": ["Chrome_WidgetWin_1", "slack_frame"],
        "process_names": ["slack.exe"],
        "title_patterns": ["Slack"],
        "search_shortcut": ["ctrl", "k"],
    },
    "discord": {
        "class_names": ["Chrome_WidgetWin_1"],
        "process_names": ["discord.exe"],
        "title_patterns": ["Discord"],
        "search_shortcut": ["ctrl", "k"],
    },
    "microsoft teams": {
        "class_names": ["Chrome_WidgetWin_1", "TeamsWebView"],
        "process_names": ["teams.exe"],
        "title_patterns": ["Microsoft Teams", "Teams"],
        "search_shortcut": ["ctrl", "e"],
    },
    
    # Development Tools
    "windows terminal": {
        "class_names": ["CASCADIA_HOSTING_WINDOW_CLASS"],
        "process_names": ["WindowsTerminal.exe"],
        "title_patterns": ["Windows Terminal", "Terminal"],
        "search_shortcut": ["ctrl", "shift", "f"],
    },
    "command prompt": {
        "class_names": ["ConsoleWindowClass"],
        "process_names": ["cmd.exe"],
        "title_patterns": ["Command Prompt", "cmd"],
        "search_shortcut": ["ctrl", "f"],
    },
    "powershell": {
        "class_names": ["ConsoleWindowClass"],
        "process_names": ["powershell.exe"],
        "title_patterns": ["PowerShell", "Windows PowerShell"],
        "search_shortcut": ["ctrl", "f"],
    },
    
    # Adobe
    "adobe acrobat": {
        "class_names": ["AdobeAcrobat"],
        "process_names": ["Acrobat.exe", "AcroRd32.exe"],
        "title_patterns": ["Adobe Acrobat", "Acrobat"],
        "search_shortcut": ["ctrl", "f"],
    },
    
    # System Utilities
    "notepad": {
        "class_names": ["Notepad"],
        "process_names": ["notepad.exe"],
        "title_patterns": ["Notepad"],
        "search_shortcut": ["ctrl", "f"],
    },
    "calculator": {
        "class_names": ["ApplicationFrameWindow", "CalcFrame"],
        "process_names": ["Calculator.exe"],
        "title_patterns": ["Calculator"],
        "search_shortcut": None,
    },
}


def get_app_profile(name: str) -> dict[str, Any] | None:
    """Look up an application profile by name (fuzzy match)."""
    key = name.strip().lower()
    
    # Exact match
    if key in SUPPORTED_APPS:
        return SUPPORTED_APPS[key]
    
    # Fuzzy match
    for known, profile in SUPPORTED_APPS.items():
        if known in key or key in known:
            return profile
    
    return None


# ---------------------------------------------------------------------------
# Win32 helpers (ctypes-based, no pywin32 dependency for basic ops)
# ---------------------------------------------------------------------------
try:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    _EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    _GetWindowTextW = _user32.GetWindowTextW
    _GetWindowTextLengthW = _user32.GetWindowTextLengthW
    _GetClassNameW = _user32.GetClassNameW
    _IsWindowVisible = _user32.IsWindowVisible
    _SetForegroundWindow = _user32.SetForegroundWindow
    _ShowWindow = _user32.ShowWindow
    _GetForegroundWindow = _user32.GetForegroundWindow
    _GetWindowRect = _user32.GetWindowRect
    _GetClientRect = _user32.GetClientRect
    _GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
    _IsIconic = _user32.IsIconic
    _IsZoomed = _user32.IsZoomed
    _AllowSetForegroundWindow = _user32.AllowSetForegroundWindow

    HAS_WIN32 = True
except Exception:
    HAS_WIN32 = False
    logger.warning("Win32 API not available; window detection disabled.")


def _window_title(hwnd: int) -> str:
    """Get the window title for a given HWND."""
    length = _GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(length)
    _GetWindowTextW(hwnd, buf, length)
    return buf.value


def _window_class(hwnd: int) -> str:
    """Get the window class name for a given HWND."""
    buf = ctypes.create_unicode_buffer(256)
    _GetClassNameW(hwnd, buf, 256)
    return buf.value


def _get_process_name(pid: int) -> str:
    """Get process name from PID."""
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.name().lower()
    except Exception:
        return "unknown"


def _enum_windows() -> list[WindowInfo]:
    """Enumerate all top-level windows via EnumWindows."""
    windows: list[WindowInfo] = []

    def _callback(hwnd: int, _lparam: int) -> bool:
        if not _IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if not title:
            return True
        cls = _window_class(hwnd)
        pid = wintypes.DWORD()
        _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wintypes.RECT()
        _GetWindowRect(hwnd, ctypes.byref(rect))
        info = WindowInfo(
            hwnd=hwnd,
            title=title,
            class_name=cls,
            process_id=pid.value,
            rect=(rect.left, rect.top, rect.right, rect.bottom),
        )
        windows.append(info)
        return True

    proc = _EnumWindowsProc(_callback)
    _user32.EnumWindows(proc, 0)
    return windows


# ---------------------------------------------------------------------------
# StrictWindowValidator - Prevents false window matches
# ---------------------------------------------------------------------------
class StrictWindowValidator:
    """Validates windows actually belong to requested apps.
    
    Prevents issues like:
    - Apple Music matching to Chrome
    - Microsoft Store matching to Settings
    - Generic classes (Chrome_WidgetWin_1) matching wrong apps
    """
    
    # Generic classes that need extra verification
    GENERIC_CLASSES = ['Chrome_WidgetWin_1', 'ApplicationFrameWindow', 'Edge_WidgetWin_0']
    
    # App-specific process mappings
    APP_PROCESS_MAP = {
        'apple music': ['applemusic.exe', 'music.ui.exe'],
        'microsoft store': ['winstore.app.exe'],
        'spotify': ['spotify.exe'],
        'brave': ['brave.exe'],
        'chrome': ['chrome.exe'],
        'vs code': ['code.exe'],
        'visual studio code': ['code.exe'],
        'microsoft edge': ['msedge.exe'],
    }
    
    @classmethod
    def validate_window(cls, app_name: str, window_title: str, window_class: str, hwnd: int) -> Dict[str, Any]:
        """
        Validate if a window belongs to the requested app.
        
        Returns:
            {
                'valid': bool,
                'confidence': float (0-1),
                'reason': str,
                'process_name': str,
                'matched_by': str
            }
        """
        app_lower = app_name.strip().lower()
        title_lower = window_title.lower()
        
        # Get process name
        process_name = _get_process_name(cls._get_pid_from_hwnd(hwnd))
        
        # Check for specific app matches first
        validation = cls._check_specific_app(app_lower, title_lower, process_name, window_class)
        if validation:
            return validation
        
        # Generic class handling
        if window_class in cls.GENERIC_CLASSES:
            # Must have app name in title or process
            if app_lower in title_lower or app_lower in process_name:
                return {
                    'valid': True,
                    'confidence': 0.70,
                    'reason': f'Generic class {window_class} with context',
                    'process_name': process_name,
                    'matched_by': 'generic_with_context'
                }
            else:
                return {
                    'valid': False,
                    'confidence': 0.0,
                    'reason': f'Generic class {window_class} without app context (title: {window_title[:50]})',
                    'process_name': process_name,
                    'matched_by': 'none'
                }
        
        # Default: accept with lower confidence
        return {
            'valid': True,
            'confidence': 0.60,
            'reason': 'Basic match',
            'process_name': process_name,
            'matched_by': 'basic'
        }
    
    @classmethod
    def _check_specific_app(cls, app_lower: str, title_lower: str, process_name: str, window_class: str) -> Optional[Dict]:
        """Check specific app validation rules."""
        
        # Apple Music
        if 'apple music' in app_lower or 'applemusic' in app_lower:
            if 'applemusic' in process_name:
                return {
                    'valid': True,
                    'confidence': 0.95,
                    'reason': 'Apple Music process match',
                    'process_name': process_name,
                    'matched_by': 'process'
                }
            if 'apple music' in title_lower:
                return {
                    'valid': True,
                    'confidence': 0.85,
                    'reason': 'Apple Music title match',
                    'process_name': process_name,
                    'matched_by': 'title'
                }
            # Reject if it's Chrome
            if 'chrome' in process_name or 'chrome' in title_lower:
                return {
                    'valid': False,
                    'confidence': 0.0,
                    'reason': 'Window belongs to Chrome, not Apple Music',
                    'process_name': process_name,
                    'matched_by': 'none'
                }
        
        # Microsoft Store
        if 'microsoft store' in app_lower or 'store' in app_lower:
            if 'winstore' in process_name:
                return {
                    'valid': True,
                    'confidence': 0.95,
                    'reason': 'Microsoft Store process match',
                    'process_name': process_name,
                    'matched_by': 'process'
                }
            if 'microsoft store' in title_lower:
                return {
                    'valid': True,
                    'confidence': 0.85,
                    'reason': 'Microsoft Store title match',
                    'process_name': process_name,
                    'matched_by': 'title'
                }
            # Reject if it's Settings
            if 'settings' in title_lower:
                return {
                    'valid': False,
                    'confidence': 0.0,
                    'reason': 'Window is Settings, not Microsoft Store',
                    'process_name': process_name,
                    'matched_by': 'none'
                }
        
        # Spotify
        if 'spotify' in app_lower:
            if 'spotify' in process_name:
                return {
                    'valid': True,
                    'confidence': 0.95,
                    'reason': 'Spotify process match',
                    'process_name': process_name,
                    'matched_by': 'process'
                }
            if 'spotify' in title_lower:
                return {
                    'valid': True,
                    'confidence': 0.85,
                    'reason': 'Spotify title match',
                    'process_name': process_name,
                    'matched_by': 'title'
                }
        
        # VS Code
        if 'vs code' in app_lower or 'visual studio code' in app_lower:
            if 'code.exe' in process_name:
                return {
                    'valid': True,
                    'confidence': 0.95,
                    'reason': 'VS Code process match',
                    'process_name': process_name,
                    'matched_by': 'process'
                }
            if 'visual studio code' in title_lower or 'vs code' in title_lower:
                return {
                    'valid': True,
                    'confidence': 0.85,
                    'reason': 'VS Code title match',
                    'process_name': process_name,
                    'matched_by': 'title'
                }
        
        return None
    
    @staticmethod
    def _get_pid_from_hwnd(hwnd: int) -> int:
        """Get process ID from window handle."""
        pid = wintypes.DWORD()
        _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    
    @classmethod
    def wait_for_valid_window(cls, app_name: str, timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        """Wait for a valid window that actually belongs to the app."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            for window in _enum_windows():
                validation = cls.validate_window(
                    app_name, window.title, window.class_name, window.hwnd
                )
                if validation['valid'] and validation['confidence'] >= 0.7:
                    return {
                        'hwnd': window.hwnd,
                        'title': window.title,
                        'class': window.class_name,
                        'process': validation['process_name'],
                        'confidence': validation['confidence'],
                        'matched_by': validation['matched_by']
                    }
            time.sleep(0.5)
        
        return None


# ---------------------------------------------------------------------------
# WindowManager
# ---------------------------------------------------------------------------
class WindowManager:
    """Win32-based window detection, focus, and wait utilities."""

    @staticmethod
    def find_window(
        title_pattern: str | None = None,
        class_name: str | None = None,
        process_id: int | None = None,
    ) -> WindowInfo | None:
        """Find the first visible window matching given criteria."""
        if not HAS_WIN32:
            return None
        for w in _enum_windows():
            if title_pattern and title_pattern.lower() not in w.title.lower():
                continue
            if class_name and class_name != w.class_name:
                continue
            if process_id is not None and process_id != w.process_id:
                continue
            return w
        return None

    @staticmethod
    def find_windows(
        title_pattern: str | None = None,
        class_name: str | None = None,
    ) -> list[WindowInfo]:
        """Find all visible windows matching given criteria."""
        if not HAS_WIN32:
            return []
        results: list[WindowInfo] = []
        for w in _enum_windows():
            if title_pattern and title_pattern.lower() not in w.title.lower():
                continue
            if class_name and class_name != w.class_name:
                continue
            results.append(w)
        return results

    @staticmethod
    def get_active_window() -> WindowInfo | None:
        """Get the currently focused foreground window."""
        if not HAS_WIN32:
            return None
        hwnd = _GetForegroundWindow()
        if not hwnd:
            return None
        title = _window_title(hwnd)
        cls = _window_class(hwnd)
        pid = wintypes.DWORD()
        _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wintypes.RECT()
        _GetWindowRect(hwnd, ctypes.byref(rect))
        return WindowInfo(
            hwnd=hwnd,
            title=title,
            class_name=cls,
            process_id=pid.value,
            rect=(rect.left, rect.top, rect.right, rect.bottom),
        )

    @staticmethod
    def focus_window(window: WindowInfo | int) -> bool:
        """Bring a window to the foreground."""
        if not HAS_WIN32:
            return False
        hwnd = window.hwnd if isinstance(window, WindowInfo) else window
        if _IsIconic(hwnd):
            _ShowWindow(hwnd, 9)  # SW_RESTORE
        _SetForegroundWindow(hwnd)
        time.sleep(0.2)
        return _GetForegroundWindow() == hwnd

    @staticmethod
    def is_focused(window: WindowInfo | int) -> bool:
        """Check if a window is currently the foreground window."""
        if not HAS_WIN32:
            return False
        hwnd = window.hwnd if isinstance(window, WindowInfo) else window
        return _GetForegroundWindow() == hwnd

    @staticmethod
    def ensure_focused(window: WindowInfo | int) -> bool:
        """Focus a window if not already focused. Returns True if focused."""
        if not HAS_WIN32:
            return False
        hwnd = window.hwnd if isinstance(window, WindowInfo) else window
        if _GetForegroundWindow() == hwnd:
            return True
        return WindowManager.focus_window(hwnd)

    @staticmethod
    def wait_for_window(
        title_pattern: str,
        class_name: str | None = None,
        timeout: float = 15.0,
        interval: float = 0.5,
    ) -> WindowInfo | None:
        """Poll until a matching window appears or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            w = WindowManager.find_window(
                title_pattern=title_pattern, class_name=class_name
            )
            if w:
                return w
            time.sleep(interval)
        return None

    @staticmethod
    def find_window_by_process_name(
        process_name: str,
    ) -> WindowInfo | None:
        """Find a window belonging to a given process name."""
        process_name = process_name.lower()
        for w in _enum_windows():
            try:
                proc_name = _get_process_name(w.process_id)
                if proc_name == process_name:
                    return w
            except Exception:
                continue
        return None
    
    @staticmethod
    def find_window_for_app(app_name: str) -> Optional[Dict[str, Any]]:
        """Find a validated window for the given app name."""
        profile = get_app_profile(app_name)
        if not profile:
            return None
        
        # Try process match first (most reliable)
        for proc_name in profile.get('process_names', []):
            window = WindowManager.find_window_by_process_name(proc_name)
            if window:
                validation = StrictWindowValidator.validate_window(
                    app_name, window.title, window.class_name, window.hwnd
                )
                if validation['valid']:
                    return {
                        'hwnd': window.hwnd,
                        'title': window.title,
                        'class': window.class_name,
                        'process': proc_name,
                        'confidence': validation['confidence']
                    }
        
        # Try title patterns
        for pattern in profile.get('title_patterns', []):
            window = WindowManager.find_window(title_pattern=pattern)
            if window:
                validation = StrictWindowValidator.validate_window(
                    app_name, window.title, window.class_name, window.hwnd
                )
                if validation['valid']:
                    return {
                        'hwnd': window.hwnd,
                        'title': window.title,
                        'class': window.class_name,
                        'process': _get_process_name(window.process_id),
                        'confidence': validation['confidence']
                    }
        
        # Try exact title
        if profile.get('exact_title'):
            window = WindowManager.find_window(title_pattern=profile['exact_title'])
            if window:
                validation = StrictWindowValidator.validate_window(
                    app_name, window.title, window.class_name, window.hwnd
                )
                if validation['valid']:
                    return {
                        'hwnd': window.hwnd,
                        'title': window.title,
                        'class': window.class_name,
                        'process': _get_process_name(window.process_id),
                        'confidence': validation['confidence']
                    }
        
        return None


# ---------------------------------------------------------------------------
# ElementLocator
# ---------------------------------------------------------------------------
class ElementLocator:
    """Find UI elements via accessibility API (pywinauto) with image fallback."""

    def __init__(self) -> None:
        self._pywinauto_available = self._check_pywinauto()
        self._pyautogui_available = self._check_pyautogui()

    @staticmethod
    def _check_pywinauto() -> bool:
        try:
            import pywinauto  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_pyautogui() -> bool:
        try:
            import pyautogui  # noqa: F401
            return True
        except ImportError:
            return False

    def find_by_automation_id(
        self,
        hwnd: int,
        automation_id: str,
        control_type: str = "Edit",
    ) -> ElementInfo | None:
        """Find a child element by automation_id via pywinauto."""
        if not self._pywinauto_available:
            return None
        try:
            from pywinauto import Desktop, Application

            app = Application().connect(handle=hwnd)
            dlg = app.window(handle=hwnd)
            ctrl = dlg.child_window(
                auto_id=automation_id, control_type=control_type
            )
            if ctrl.exists(timeout=2):
                rect = ctrl.rectangle()
                return ElementInfo(
                    control_type=control_type,
                    automation_id=automation_id,
                    class_name=ctrl.element_info.class_name or "",
                    name=ctrl.element_info.name or "",
                    rect=(rect.left, rect.top, rect.right, rect.bottom),
                    is_enabled=ctrl.is_enabled(),
                )
        except Exception:
            logger.debug("find_by_automation_id failed", exc_info=True)
        return None

    def find_by_text(
        self,
        hwnd: int,
        text: str,
        control_type: str = "Edit",
    ) -> ElementInfo | None:
        """Find a child element by its display text via pywinauto."""
        if not self._pywinauto_available:
            return None
        try:
            from pywinauto import Application

            app = Application().connect(handle=hwnd)
            ctrl = app.window(handle=hwnd).child_window(
                title=text, control_type=control_type
            )
            if ctrl.exists(timeout=2):
                rect = ctrl.rectangle()
                return ElementInfo(
                    control_type=control_type,
                    automation_id="",
                    class_name=ctrl.element_info.class_name or "",
                    name=text,
                    rect=(rect.left, rect.top, rect.right, rect.bottom),
                    is_enabled=ctrl.is_enabled(),
                )
        except Exception:
            logger.debug("find_by_text failed", exc_info=True)
        return None

    def find_by_class_name(
        self,
        hwnd: int,
        class_name: str,
        control_type: str = "Edit",
    ) -> ElementInfo | None:
        """Find a child element by class_name via pywinauto."""
        if not self._pywinauto_available:
            return None
        try:
            from pywinauto import Application

            app = Application().connect(handle=hwnd)
            ctrl = app.window(handle=hwnd).child_window(
                class_name=class_name, control_type=control_type
            )
            if ctrl.exists(timeout=2):
                rect = ctrl.rectangle()
                return ElementInfo(
                    control_type=control_type,
                    automation_id="",
                    class_name=class_name,
                    name=ctrl.element_info.name or "",
                    rect=(rect.left, rect.top, rect.right, rect.bottom),
                    is_enabled=ctrl.is_enabled(),
                )
        except Exception:
            logger.debug("find_by_class_name failed", exc_info=True)
        return None

    def find_first_edit(self, hwnd: int) -> ElementInfo | None:
        """Find the first enabled Edit control in a window."""
        if self._pywinauto_available:
            try:
                from pywinauto import Application

                app = Application().connect(handle=hwnd)
                for ctrl in app.window(handle=hwnd).descendants(
                    control_type="Edit"
                ):
                    if ctrl.is_enabled():
                        rect = ctrl.rectangle()
                        return ElementInfo(
                            control_type="Edit",
                            automation_id=ctrl.element_info.automation_id or "",
                            class_name=ctrl.element_info.class_name or "",
                            name=ctrl.element_info.name or "",
                            rect=(
                                rect.left,
                                rect.top,
                                rect.right,
                                rect.bottom,
                            ),
                            is_enabled=True,
                        )
            except Exception:
                logger.debug("find_first_edit failed", exc_info=True)
        return None

    def find_by_image(
        self, image_path: str, confidence: float = 0.8
    ) -> tuple[int, int] | None:
        """Find an image on screen via PyAutoGUI. Returns (x, y) center."""
        if not self._pyautogui_available:
            return None
        try:
            import pyautogui

            pos = pyautogui.locateOnScreen(image_path, confidence=confidence)
            if pos:
                return pyautogui.center(pos)
        except Exception:
            logger.debug("find_by_image failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
def retry(
    fn: Callable[..., Any],
    max_attempts: int = 3,
    delay: float = 0.5,
    args: tuple = (),
    kwargs: dict | None = None,
) -> tuple[bool, Any]:
    """Execute a function with up to `max_attempts` retries."""
    if kwargs is None:
        kwargs = {}
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn(*args, **kwargs)
            if result is not None and result is not False:
                return (True, result)
            if result is True:
                return (True, result)
        except Exception as exc:
            last_exc = exc
            logger.debug(
                "Attempt %d/%d failed: %s", attempt, max_attempts, exc
            )
        if attempt < max_attempts:
            time.sleep(delay)
    return (False, last_exc)


# ---------------------------------------------------------------------------
# UIAutomator (top-level facade)
# ---------------------------------------------------------------------------
class UIAutomator:
    """Unified facade combining WindowManager, ElementLocator, and safety."""

    def __init__(self) -> None:
        self.wm = WindowManager()
        self.el = ElementLocator()
        self.validator = StrictWindowValidator()
        self.max_attempts = 3
        self.retry_delay = 0.5

    # ---- Safety helpers ----

    def _ensure_window_focused(self, window: WindowInfo) -> bool:
        """Verify a window is focused; focus it if not. Returns True if
        focused after the attempt."""
        ok, _ = retry(
            self.wm.ensure_focused,
            max_attempts=3,
            delay=0.3,
            args=(window,),
        )
        return ok

    def _safety_check(self, window: WindowInfo | None) -> bool:
        """Pre-click safety: target must exist and be focused."""
        if window is None:
            logger.warning("Safety check failed: no target window")
            return False
        return self._ensure_window_focused(window)

    # ---- Window actions ----

    def focus_window(
        self, title: str, class_name: str | None = None
    ) -> str:
        """Find and focus a window by title pattern."""
        window = self.wm.find_window(
            title_pattern=title, class_name=class_name
        )
        if not window:
            return f"Could not find window matching '{title}', sir."
        if self._ensure_window_focused(window):
            session["current_window"] = window.title
            return f"Focused {window.title}, sir."
        return f"Failed to focus {title}, sir."

    def wait_for_window(
        self,
        title_pattern: str,
        class_name: str | None = None,
        timeout: float = 15.0,
    ) -> str:
        """Wait for a window to appear, then focus it."""
        window = self.wm.wait_for_window(
            title_pattern=title_pattern,
            class_name=class_name,
            timeout=timeout,
        )
        if not window:
            return (
                f"Window '{title_pattern}' did not appear within "
                f"{timeout:.0f}s, sir."
            )
        if self._ensure_window_focused(window):
            session["current_window"] = window.title
            return f"Window '{window.title}' is ready, sir."
        return f"Found but could not focus '{title_pattern}', sir."

    # ---- Mouse actions ----

    def click(
        self,
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
        target_window: WindowInfo | None = None,
    ) -> str:
        if not self._safety_check(target_window):
            return "Click cancelled, sir."
        ok, result = retry(
            self._do_click,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            args=(x, y, button),
        )
        if ok:
            loc = f" at ({x}, {y})" if x is not None else ""
            return f"{button.title()} clicked{loc}, sir."
        return f"Click failed after {self.max_attempts} attempts, sir."

    def _do_click(self, x: int | None, y: int | None, button: str) -> bool:
        try:
            import pyautogui

            pyautogui.click(x, y, button=button)
            return True
        except Exception:
            return False

    def double_click(
        self,
        x: int | None = None,
        y: int | None = None,
        target_window: WindowInfo | None = None,
    ) -> str:
        if not self._safety_check(target_window):
            return "Double-click cancelled, sir."
        ok, _ = retry(
            self._do_double_click,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            args=(x, y),
        )
        if ok:
            return "Double-clicked, sir."
        return f"Double-click failed after {self.max_attempts} attempts, sir."

    def _do_double_click(self, x: int | None, y: int | None) -> bool:
        try:
            import pyautogui

            pyautogui.doubleClick(x, y)
            return True
        except Exception:
            return False

    def right_click(
        self,
        x: int | None = None,
        y: int | None = None,
        target_window: WindowInfo | None = None,
    ) -> str:
        if not self._safety_check(target_window):
            return "Right-click cancelled, sir."
        ok, _ = retry(
            self._do_right_click,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            args=(x, y),
        )
        if ok:
            return "Right-clicked, sir."
        return (
            f"Right-click failed after {self.max_attempts} attempts, sir."
        )

    def _do_right_click(self, x: int | None, y: int | None) -> bool:
        try:
            import pyautogui

            pyautogui.rightClick(x, y)
            return True
        except Exception:
            return False

    def move_mouse(
        self,
        x: int,
        y: int,
        duration: float = 0.3,
    ) -> str:
        try:
            import pyautogui

            pyautogui.moveTo(x, y, duration=duration)
            return f"Mouse moved to ({x}, {y}), sir."
        except Exception as exc:
            return f"Mouse move failed, sir. {exc}"

    # ---- Keyboard actions ----

    def type_text(self, text: str, interval: float = 0.05) -> str:
        if not text:
            return "Nothing to type, sir."
        ok, _ = retry(
            self._do_type_text,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            args=(text, interval),
        )
        if ok:
            return "Typed the text, sir."
        return "Typing failed, sir."

    def _do_type_text(self, text: str, interval: float) -> bool:
        try:
            import pyautogui

            pyautogui.typewrite(text, interval=interval)
            return True
        except Exception:
            return False

    def press_key(self, key: str, presses: int = 1) -> str:
        if not key:
            return "No key specified, sir."
        ok, _ = retry(
            self._do_press_key,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            args=(key, presses),
        )
        if ok:
            return f"Pressed {key}, sir."
        return f"Key press '{key}' failed, sir."

    def _do_press_key(self, key: str, presses: int) -> bool:
        try:
            import pyautogui

            pyautogui.press(key, presses=presses)
            return True
        except Exception:
            return False

    def hotkey(self, *keys: str) -> str:
        """Press a combination of keys simultaneously."""
        if not keys:
            return "No hotkey specified, sir."
        ok, _ = retry(
            self._do_hotkey,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            args=keys,
        )
        if ok:
            label = "+".join(keys)
            return f"Pressed {label}, sir."
        return f"Hotkey {'+'.join(keys)} failed, sir."

    def _do_hotkey(self, *keys: str) -> bool:
        try:
            import pyautogui

            pyautogui.hotkey(*keys)
            return True
        except Exception:
            return False

    # ---- Scroll ----

    def scroll(
        self,
        direction: str = "down",
        amount: int = 3,
        x: int | None = None,
        y: int | None = None,
    ) -> str:
        clicks = -amount if direction in ("down", "right") else amount
        ok, _ = retry(
            self._do_scroll,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            args=(clicks, x, y),
        )
        if ok:
            return f"Scrolled {direction}, sir."
        return f"Scroll failed after {self.max_attempts} attempts, sir."

    def _do_scroll(self, clicks: int, x: int | None, y: int | None) -> bool:
        try:
            import pyautogui

            pyautogui.scroll(clicks, x, y)
            return True
        except Exception:
            return False

    # ---- Search in app ----

    def search_in_app(
        self,
        query: str,
        app: str,
        window_hwnd: int = None,
    ) -> str:
        """Execute a search inside a target application with validation."""
        if not query:
            return "Nothing to search for, sir."
        
        # Get app profile
        profile = get_app_profile(app)
        if profile is None:
            return f"'{app}' is not a supported application for search, sir."
        
        # Find window with validation
        if window_hwnd:
            # Validate provided window
            window = None
            for w in _enum_windows():
                if w.hwnd == window_hwnd:
                    window = w
                    break
            
            if window:
                validation = self.validator.validate_window(
                    app, window.title, window.class_name, window.hwnd
                )
                if not validation['valid']:
                    return f"Cannot search in {app} - current window is {window.title} ({validation['reason']}), sir."
        else:
            # Find valid window
            window_info = self.validator.wait_for_valid_window(app, timeout=10.0)
            if not window_info:
                return f"Could not find a valid {app} window, sir."
            window_hwnd = window_info['hwnd']
        
        # Focus the window
        if not self.wm.focus_window(window_hwnd):
            return f"Could not focus {app}, sir."
        
        time.sleep(0.5)  # Wait for focus to settle
        
        # Try keyboard shortcut first
        if profile.get("search_shortcut"):
            shortcut = profile["search_shortcut"]
            self._do_hotkey(*shortcut)
            time.sleep(0.5)
            self._do_type_text(query, 0.05)
            self._do_press_key("enter", 1)
            return f"Searching for '{query}' in {app}, sir."
        
        # Try accessibility
        elem = self.el.find_first_edit(window_hwnd)
        if elem and elem.rect:
            cx, cy = elem.center
            self._do_click(cx, cy, "left")
            time.sleep(0.3)
            self._do_type_text(query, 0.05)
            self._do_press_key("enter", 1)
            return f"Searching for '{query}' in {app}, sir."
        
        return f"Could not locate the search box in {app}, sir."


# ---------------------------------------------------------------------------
# Singleton instances for import convenience
# ---------------------------------------------------------------------------
automator = UIAutomator()
# Add to ui_core.py - Fix missing universal_search import

# UniversalSearchEngine stub for compatibility
class UniversalSearchEngine:
    def __init__(self, automator):
        self.automator = automator
    
    def search(self, query: str, app: str) -> str:
        """Stub for compatibility - uses the new search_agent"""
        from search_agent import search_agent
        from ui_core import WindowManager
        
        wm = WindowManager()
        active = wm.get_active_window()
        
        if not active:
            return f"No active window to search in {app}, sir."
        
        result = search_agent.search(query, app, active.hwnd)
        return result.message


# Create global instance
universal_search = UniversalSearchEngine(automator)