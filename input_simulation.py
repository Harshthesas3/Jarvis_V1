"""
input_simulation.py
-------------------
Keyboard/mouse simulation for JARVIS. Wraps pyautogui for automation:
click, double_click, right_click, type_text, press_key, scroll.

Public API:
    click(x=None, y=None, button='left')
    double_click(x=None, y=None)
    right_click(x=None, y=None)
    move_mouse(x, y, duration=0.3)
    type_text(text, interval=0.05)
    press_key(key, presses=1)
    hotkey(*keys)
    scroll(clicks, x=None, y=None)
"""

from __future__ import annotations

import logging

logger = logging.getLogger("jarvis.input")

_IMPORT_ERROR: str | None = None

def _ensure_pyautogui():
    global _IMPORT_ERROR
    if _IMPORT_ERROR:
        raise ImportError(_IMPORT_ERROR)
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        return pyautogui
    except ImportError as exc:
        _IMPORT_ERROR = str(exc)
        raise


def click(x: int | None = None, y: int | None = None, button: str = "left") -> str:
    try:
        pg = _ensure_pyautogui()
        if x is not None and y is not None:
            pg.click(x, y, button=button)
            return f"Clicked at ({x}, {y}), sir."
        pg.click(button=button)
        return f"{button.title()} clicked, sir."
    except ImportError:
        return "Mouse simulation is unavailable, sir. PyAutoGUI is not installed."
    except Exception as exc:
        logger.exception("click failed")
        return f"Click failed, sir. {exc}"


def double_click(x: int | None = None, y: int | None = None) -> str:
    try:
        pg = _ensure_pyautogui()
        if x is not None and y is not None:
            pg.doubleClick(x, y)
            return f"Double-clicked at ({x}, {y}), sir."
        pg.doubleClick()
        return "Double-clicked, sir."
    except ImportError:
        return "Mouse simulation is unavailable, sir. PyAutoGUI is not installed."
    except Exception as exc:
        logger.exception("double_click failed")
        return f"Double-click failed, sir. {exc}"


def right_click(x: int | None = None, y: int | None = None) -> str:
    try:
        pg = _ensure_pyautogui()
        if x is not None and y is not None:
            pg.rightClick(x, y)
            return f"Right-clicked at ({x}, {y}), sir."
        pg.rightClick()
        return "Right-clicked, sir."
    except ImportError:
        return "Mouse simulation is unavailable, sir. PyAutoGUI is not installed."
    except Exception as exc:
        logger.exception("right_click failed")
        return f"Right-click failed, sir. {exc}"


def type_text(text: str, interval: float = 0.05) -> str:
    if not text:
        return "Nothing to type, sir."
    try:
        pg = _ensure_pyautogui()
        pg.typewrite(text, interval=interval)
        return "Typed the text, sir."
    except ImportError:
        return "Keyboard simulation is unavailable, sir. PyAutoGUI is not installed."
    except Exception as exc:
        logger.exception("type_text failed")
        return f"Typing failed, sir. {exc}"


def press_key(key: str, presses: int = 1) -> str:
    if not key:
        return "No key specified, sir."
    try:
        pg = _ensure_pyautogui()
        pg.press(key, presses=presses)
        return f"Pressed {key}, sir."
    except ImportError:
        return "Keyboard simulation is unavailable, sir. PyAutoGUI is not installed."
    except Exception as exc:
        logger.exception("press_key failed")
        return f"Key press failed, sir. {exc}"


def hotkey(*keys: str) -> str:
    """Press a combination of keys simultaneously (e.g. hotkey('ctrl', 'l'))."""
    if not keys:
        return "No hotkey specified, sir."
    try:
        pg = _ensure_pyautogui()
        pg.hotkey(*keys)
        label = "+".join(keys)
        return f"Pressed {label}, sir."
    except ImportError:
        return "Keyboard simulation is unavailable, sir. PyAutoGUI is not installed."
    except Exception as exc:
        logger.exception("hotkey failed")
        return f"Hotkey failed, sir. {exc}"


def move_mouse(x: int, y: int, duration: float = 0.3) -> str:
    """Move the mouse to absolute screen coordinates."""
    try:
        pg = _ensure_pyautogui()
        pg.moveTo(x, y, duration=duration)
        return f"Mouse moved to ({x}, {y}), sir."
    except ImportError:
        return "Mouse simulation is unavailable, sir. PyAutoGUI is not installed."
    except Exception as exc:
        logger.exception("move_mouse failed")
        return f"Mouse move failed, sir. {exc}"


def scroll(clicks: int, x: int | None = None, y: int | None = None) -> str:
    try:
        pg = _ensure_pyautogui()
        if x is not None and y is not None:
            pg.scroll(clicks, x, y)
        else:
            pg.scroll(clicks)
        direction = "down" if clicks < 0 else "up"
        return f"Scrolled {direction}, sir."
    except ImportError:
        return "Scroll simulation is unavailable, sir. PyAutoGUI is not installed."
    except Exception as exc:
        logger.exception("scroll failed")
        return f"Scroll failed, sir. {exc}"
