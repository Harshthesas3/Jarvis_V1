"""
search_agent.py - Fixed version that actually verifies window focus before searching
"""

import logging
import time
import re
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

logger = logging.getLogger("jarvis.search_agent")

class SearchMethod(Enum):
    ACCESSIBILITY = "accessibility"
    AUTOMATION_ID = "automation_id"
    OCR = "ocr"
    KEYBOARD_SHORTCUT = "keyboard_shortcut"
    VISION = "vision"


class PrioritizedSearchAgent:
    """Prioritized search engine that verifies window focus first."""
    
    APP_SHORTCUTS = {
        "apple music": ["ctrl", "f"],
        "spotify": ["ctrl", "l"],
        "brave": ["ctrl", "l"],
        "chrome": ["ctrl", "l"],
        "microsoft edge": ["ctrl", "l"],
        "microsoft store": ["ctrl", "f"],
        "file explorer": ["ctrl", "e"],
        "vs code": ["ctrl", "p"],
    }
    
    def __init__(self):
        self._method_cache = {}
    
    def search(self, query: str, app_name: str, window_hwnd: int = None) -> 'SearchResult':
        from ui_core import WindowManager, automator
        
        if not query or not query.strip():
            return SearchResult(False, "Nothing to search for, sir.")
        
        wm = WindowManager()
        
        # Get active window
        active = wm.get_active_window()
        if not active:
            return SearchResult(False, "No active window found, sir.")
        
        # Verify we have the right window
        if window_hwnd and active.hwnd != window_hwnd:
            logger.warning(f"Window mismatch: expected {window_hwnd}, active {active.hwnd}")
            # Try to focus the correct window
            if not wm.focus_window(window_hwnd):
                return SearchResult(False, f"Could not focus {app_name} window, sir.")
            time.sleep(0.5)
            active = wm.get_active_window()
        
        # Validate window belongs to app
        if not self._validate_window(app_name, active.title, active.class_name, active.hwnd):
            return SearchResult(False, f"Cannot search: Current window '{active.title}' is not {app_name}, sir.")
        
        # Try keyboard shortcut first (most reliable)
        app_lower = app_name.lower()
        shortcut = self.APP_SHORTCUTS.get(app_lower)
        
        if shortcut:
            logger.info(f"Using keyboard shortcut {shortcut} for {app_name}")
            automator._do_hotkey(*shortcut)
            time.sleep(0.5)
            automator._do_type_text(query, 0.05)
            automator._do_press_key("enter", 1)
            return SearchResult(True, f"Searching for '{query}' in {app_name}, sir.", SearchMethod.KEYBOARD_SHORTCUT)
        
        # Fallback to accessibility
        try:
            from pywinauto import Application
            app = Application().connect(handle=active.hwnd)
            dlg = app.window(handle=active.hwnd)
            
            for ctrl in dlg.descendants(control_type=["Edit", "SearchBox"]):
                if ctrl.is_enabled():
                    rect = ctrl.rectangle()
                    cx = (rect.left + rect.right) // 2
                    cy = (rect.top + rect.bottom) // 2
                    automator._do_click(cx, cy, "left")
                    time.sleep(0.3)
                    automator._do_type_text(query, 0.05)
                    automator._do_press_key("enter", 1)
                    return SearchResult(True, f"Searching for '{query}' in {app_name}, sir.", SearchMethod.ACCESSIBILITY)
        except Exception as e:
            logger.debug(f"Accessibility search failed: {e}")
        
        return SearchResult(False, f"Could not find search field in {app_name}, sir.")
    
    def _validate_window(self, app_name: str, title: str, class_name: str, hwnd: int) -> bool:
        """Validate window actually belongs to the app."""
        from ui_core import _get_process_name
        
        app_lower = app_name.lower()
        title_lower = title.lower()
        process_name = _get_process_name(self._get_pid_from_hwnd(hwnd))
        
        # Check process match
        if app_lower in process_name.lower():
            return True
        
        # Check title match
        if app_lower in title_lower:
            return True
        
        # Special cases
        if 'apple music' in app_lower and 'apple' in title_lower:
            return True
        if 'microsoft store' in app_lower and 'store' in title_lower:
            return True
        
        logger.warning(f"Window validation failed: app={app_name}, title={title}, process={process_name}")
        return False
    
    def _get_pid_from_hwnd(self, hwnd: int) -> int:
        import ctypes
        from ctypes import wintypes
        _user32 = ctypes.windll.user32
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value


class SearchResult:
    def __init__(self, success: bool, message: str, method: Optional[SearchMethod] = None, confidence: float = 0.0):
        self.success = success
        self.message = message
        self.method = method
        self.confidence = confidence
    
    def __bool__(self):
        return self.success


search_agent = PrioritizedSearchAgent()