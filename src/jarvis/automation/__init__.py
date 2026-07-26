"""Automation package for desktop UI control."""

from jarvis.automation.app_launcher import AppLauncher
from jarvis.automation.window import WindowManager
from jarvis.automation.ui_automator import UIAutomator
from jarvis.automation.screen import ScreenCapture
from jarvis.automation.search import SearchInApp

__all__ = [
    "AppLauncher",
    "WindowManager",
    "UIAutomator",
    "ScreenCapture",
    "SearchInApp",
]
