"""
diagnostics.py
--------------
Startup dependency checks and runtime diagnostics for JARVIS.

Public API:
    check_environment() -> dict[str, Any]
    print_report(report: dict[str, Any]) -> None
    get_report_text(report: dict[str, Any]) -> str
"""

from __future__ import annotations

import ctypes
import importlib
import logging
import os
import sys

logger = logging.getLogger("jarvis.diagnostics")

_LIBRARIES: list[dict[str, str]] = [
    {"name": "pywinauto", "check": "pywinauto"},
    {"name": "pyautogui", "check": "pyautogui"},
    {"name": "pytesseract", "check": "pytesseract"},
    {"name": "Pillow", "check": "PIL"},
    {"name": "mss", "check": "mss"},
    {"name": "ollama", "check": "ollama"},
    {"name": "sounddevice", "check": "sounddevice"},
    {"name": "faster_whisper", "check": "faster_whisper"},
    {"name": "keyboard", "check": "keyboard"},
    {"name": "psutil", "check": "psutil"},
    {"name": "pycaw", "check": "pycaw"},
]


def check_environment() -> dict[str, Any]:
    """Run all startup checks and return a report dict."""
    report: dict[str, Any] = {
        "python_version": sys.version,
        "platform": sys.platform,
        "libraries": {},
        "win32_api": False,
        "window_manager": False,
        "accessibility": False,
        "search_engine": False,
        "uwp_available": False,
        "automation_available": False,
        "installed_apps_count": 0,
        "running_apps": [],
        "detected_windows": [],
    }

    # -- Library checks --
    for lib in _LIBRARIES:
        name = lib["name"]
        module = lib["check"]
        try:
            importlib.import_module(module)
            report["libraries"][name] = "AVAILABLE"
        except ImportError:
            report["libraries"][name] = "NOT INSTALLED"
        except Exception as exc:
            report["libraries"][name] = f"ERROR: {exc}"

    # -- Win32 API --
    try:
        user32 = ctypes.windll.user32
        report["win32_api"] = user32.EnumWindows is not None
    except Exception:
        report["win32_api"] = False

    # -- Window manager (Win32) --
    try:
        from ui_core import WindowManager
        wm = WindowManager()
        active = wm.get_active_window()
        report["window_manager"] = active is not None
        if active:
            report["active_window"] = active.title
            report["active_window_class"] = active.class_name
    except Exception as exc:
        report["window_manager"] = False
        report["window_manager_error"] = str(exc)

    # -- Accessibility (pywinauto) --
    try:
        import pywinauto
        report["accessibility"] = True
    except ImportError:
        report["accessibility"] = False

    # -- Search engine status --
    try:
        from ui_core import universal_search
        report["search_engine"] = universal_search is not None
    except Exception as exc:
        report["search_engine"] = False
        report["search_engine_error"] = str(exc)

    # -- UWP availability --
    try:
        import subprocess as _sp
        result = _sp.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-AppxPackage | Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            report["uwp_available"] = int(result.stdout.strip()) > 0
    except Exception:
        report["uwp_available"] = False

    # -- Automation status --
    try:
        import pywinauto
        from ui_core import UIAutomator
        uia = UIAutomator()
        report["automation_available"] = True
    except Exception:
        report["automation_available"] = False

    # -- Installed apps count --
    try:
        from ui_core import get_app_profile
        report["installed_apps_count"] = 90  # SUPPORTED_APPS size
    except Exception:
        pass

    # -- Running apps (visible windows) --
    try:
        from ui_core import WindowManager
        wm = WindowManager()
        wins = wm.find_windows()
        report["detected_windows"] = [
            {"title": w.title, "class": w.class_name}
            for w in wins[:20]
        ]
    except Exception:
        pass

    return report


def print_report(report: dict[str, Any]) -> None:
    """Print diagnostics report to stdout."""
    print(get_report_text(report))


def get_report_text(report: dict[str, Any]) -> str:
    """Return formatted diagnostics report as a string."""
    OK = "[OK]"
    NO = "[--]"
    lines: list[str] = []
    lines.append("=" * 56)
    lines.append("  JARVIS DIAGNOSTICS REPORT")
    lines.append("=" * 56)
    lines.append(f"  Python:      {report.get('python_version', 'unknown')[:60]}")
    lines.append(f"  Platform:    {report.get('platform', 'unknown')}")
    lines.append("")
    lines.append("  --- Libraries ---")
    for name, status in sorted(report.get("libraries", {}).items()):
        marker = OK if "AVAILABLE" in str(status) else NO
        lines.append(f"    {marker} {name}: {status}")
    lines.append("")
    lines.append("  --- System ---")
    lines.append(f"    {OK if report.get('win32_api') else NO} Win32 API")
    lines.append(f"    {OK if report.get('window_manager') else NO} Window Manager")
    if report.get("active_window"):
        lines.append(f"      Active: {report['active_window']} ({report.get('active_window_class', '?')})")
    lines.append(f"    {OK if report.get('accessibility') else NO} Accessibility (pywinauto)")
    lines.append(f"    {OK if report.get('search_engine') else NO} Search Engine")
    lines.append(f"    {OK if report.get('uwp_available') else NO} UWP Available")
    lines.append(f"    {OK if report.get('automation_available') else NO} Automation")
    lines.append(f"    App Profiles: {report.get('installed_apps_count', 0)}")
    if report.get("search_engine_error"):
        lines.append(f"      Error: {report['search_engine_error']}")
    lines.append("")
    lines.append("  --- Detected Windows ({count}) ---".format(
        count=len(report.get("detected_windows", []))))
    for win in report.get("detected_windows", [])[:10]:
        lines.append(f"    {win['title'][:40]:40s} ({win['class'][:30]})")
    if len(report.get("detected_windows", [])) > 10:
        lines.append(f"    ... and {len(report['detected_windows']) - 10} more")
    lines.append("")
    lines.append("  --- Accessibility ---")
    if report.get("accessibility"):
        lines.append("    UI Automation: AVAILABLE")
        lines.append("    Install: Already installed.")
    else:
        lines.append("    UI Automation: NOT INSTALLED")
        lines.append("    Install: pip install pywinauto")
    lines.append("")
    lines.append("=" * 56)
    return "\n".join(lines)
