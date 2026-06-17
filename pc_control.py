"""
pc_control.py
-------------
Windows PC control for JARVIS. Wraps the shell/launcher commands used to
lock, sleep, log off, shutdown, and restart the machine, plus shortcuts to
common shell folders and admin tools.

Public API:
    list_commands() -> list[str]
    execute(op: str, confirm_fn=None) -> dict
    is_destructive(op: str) -> bool

All public functions return a dict with at least:
    {"ok": bool, "tts": str, "op": str}

Destructive ops (shutdown, restart, log off) REQUIRE explicit confirmation
from the caller via confirm_fn. confirm_fn(prompt: str) -> bool.
If the caller passes None, the destructive action is REJECTED.

Logging is routed to the "jarvis.pc" logger.
"""

from __future__ import annotations

import logging
import os
import subprocess
import webbrowser
from typing import Callable, Optional

logger = logging.getLogger("jarvis.pc")

# ---------------------------------------------------------------------------
# Command catalog
# ---------------------------------------------------------------------------
# Each entry: (key, callable(args: dict) -> dict, destructive?)
# The callable is a small handler that runs the actual side effect.

_DESTRUCTIVE_OPS = {"shutdown", "restart", "logoff"}


def is_destructive(op: str) -> bool:
    return (op or "").strip().lower() in _DESTRUCTIVE_OPS


# ---------------------------------------------------------------------------
# Shell folder constants. Used to open "downloads", "documents", etc.
# ---------------------------------------------------------------------------
_SHELL_FOLDERS = {
    "downloads":    "shell:Downloads",
    "documents":    "shell:Personal",
    "desktop":      "shell:Desktop",
    "recycle":      "shell:RecycleBinFolder",
    "recycle_bin":  "shell:RecycleBinFolder",
    "pictures":     "shell:My Pictures",
    "music":        "shell:My Music",
    "videos":       "shell:My Video",
}

# ---------------------------------------------------------------------------
# Run a small subprocess safely. Capture and log failures; never raise.
# ---------------------------------------------------------------------------
def _run(cmd: list, *, shell: bool = False) -> tuple[bool, str]:
    try:
        kwargs = {"shell": shell, "capture_output": True, "text": True,
                  "timeout": 15}
        result = subprocess.run(cmd, **kwargs)
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            logger.warning("Command failed (%s): rc=%s err=%s",
                           cmd, result.returncode, err)
            return False, err or f"exit {result.returncode}"
        return True, ""
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out: %s", cmd)
        return False, "timeout"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Command error: %s", cmd)
        return False, str(exc)


def _spawn_detached(target: str) -> tuple[bool, str]:
    """Open a file/URL/URI without blocking."""
    try:
        if target.startswith(("http://", "https://", "shell:")):
            # explorer.exe handles shell: URIs; webbrowser handles http(s).
            if target.startswith("shell:"):
                subprocess.Popen(["explorer.exe", target],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            else:
                webbrowser.open(target)
        else:
            # Treat as a direct path / executable.
            subprocess.Popen(target, shell=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to open %s", target)
        return False, str(exc)


# ---------------------------------------------------------------------------
# Per-op handlers. Each takes confirm_fn (for destructive ops) and returns
# a dict. The dict shape matches what the executor expects to relay to TTS.
# ---------------------------------------------------------------------------
def _do_lock(_: dict) -> dict:
    ok, err = _run(["rundll32.exe", "user32.dll,LockWorkStation"])
    return {
        "ok": ok,
        "tts": "Locking computer, sir." if ok else f"Lock failed, sir. {err}",
        "op": "lock",
    }


def _do_sleep(_: dict) -> dict:
    # PowerShell-based sleep — works on Win10/11.
    ok, err = _run([
        "powershell", "-NoProfile", "-Command",
        "Add-Type -AssemblyName System.Windows.Forms; "
        "[System.Windows.Forms.Application]::SetSuspendState("
        "[System.Windows.Forms.PowerState]::Suspend, $false, $false);",
    ])
    return {
        "ok": ok,
        "tts": "Putting the computer to sleep, sir." if ok else f"Sleep failed, sir. {err}",
        "op": "sleep",
    }


def _do_logoff(args: dict) -> dict:
    confirm = args.get("confirm_fn")
    if not confirm or not confirm(
        "Are you sure you want to log off, sir? (yes/no)"
    ):
        return {"ok": False, "cancelled": True,
                "tts": "Log off cancelled, sir.", "op": "logoff"}
    ok, err = _run(["shutdown", "/l"])
    return {
        "ok": ok,
        "tts": "Logging off, sir." if ok else f"Log off failed, sir. {err}",
        "op": "logoff",
    }


def _do_shutdown(args: dict) -> dict:
    confirm = args.get("confirm_fn")
    if not confirm or not confirm(
        "Are you sure you want to SHUT DOWN the computer, sir? (yes/no)"
    ):
        return {"ok": False, "cancelled": True,
                "tts": "Shutdown cancelled, sir.", "op": "shutdown"}
    # /t 5 gives a small grace window the user can abort with `shutdown /a`.
    ok, err = _run(["shutdown", "/s", "/t", "5"])
    return {
        "ok": ok,
        "tts": "Shutting down in 5 seconds, sir. Say 'abort shutdown' to cancel."
        if ok else f"Shutdown failed, sir. {err}",
        "op": "shutdown",
    }


def _do_restart(args: dict) -> dict:
    confirm = args.get("confirm_fn")
    if not confirm or not confirm(
        "Are you sure you want to RESTART the computer, sir? (yes/no)"
    ):
        return {"ok": False, "cancelled": True,
                "tts": "Restart cancelled, sir.", "op": "restart"}
    ok, err = _run(["shutdown", "/r", "/t", "5"])
    return {
        "ok": ok,
        "tts": "Restarting in 5 seconds, sir. Say 'abort shutdown' to cancel."
        if ok else f"Restart failed, sir. {err}",
        "op": "restart",
    }


def _do_task_manager(_: dict) -> dict:
    # Use the Ctrl+Shift+Esc shortcut via PowerShell SendKeys; works even
    # if Task Manager's path changes across Windows builds.
    ok, err = _run([
        "powershell", "-NoProfile", "-Command",
        "(New-Object -ComObject WScript.Shell).SendKeys('^+{ESC}');",
    ])
    if not ok:
        # Fallback: launch taskmgr.exe directly.
        ok, err = _spawn_detached("taskmgr.exe")
    return {
        "ok": ok,
        "tts": "Opening Task Manager, sir." if ok else f"Task Manager failed, sir. {err}",
        "op": "task_manager",
    }


def _do_control_panel(_: dict) -> dict:
    ok, err = _spawn_detached("control.exe")
    return {
        "ok": ok,
        "tts": "Opening Control Panel, sir." if ok else f"Control Panel failed, sir. {err}",
        "op": "control_panel",
    }


def _do_settings(_: dict) -> dict:
    ok, err = _spawn_detached("ms-settings:")
    return {
        "ok": ok,
        "tts": "Opening Settings, sir." if ok else f"Settings failed, sir. {err}",
        "op": "settings",
    }


def _do_device_manager(_: dict) -> dict:
    ok, err = _spawn_detached("devmgmt.msc")
    return {
        "ok": ok,
        "tts": "Opening Device Manager, sir." if ok else f"Device Manager failed, sir. {err}",
        "op": "device_manager",
    }


def _do_services(_: dict) -> dict:
    ok, err = _spawn_detached("services.msc")
    return {
        "ok": ok,
        "tts": "Opening Services, sir." if ok else f"Services failed, sir. {err}",
        "op": "services",
    }


def _do_registry(_: dict) -> dict:
    ok, err = _spawn_detached("regedit.exe")
    return {
        "ok": ok,
        "tts": "Opening Registry Editor, sir." if ok else f"Registry Editor failed, sir. {err}",
        "op": "registry",
    }


def _do_shell_folder(args: dict) -> dict:
    name = (args.get("name") or "").strip().lower().replace(" ", "_")
    uri = _SHELL_FOLDERS.get(name)
    if not uri:
        return {"ok": False,
                "tts": f"I don't know how to open {name}, sir.",
                "op": "shell_folder"}
    ok, err = _spawn_detached(uri)
    return {
        "ok": ok,
        "tts": f"Opening {name.replace('_', ' ')}, sir." if ok
        else f"Failed to open {name}, sir. {err}",
        "op": "shell_folder",
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_OPS: dict[str, Callable[[dict], dict]] = {
    "lock":           _do_lock,
    "sleep":          _do_sleep,
    "logoff":         _do_logoff,
    "shutdown":       _do_shutdown,
    "restart":        _do_restart,
    "task_manager":   _do_task_manager,
    "control_panel":  _do_control_panel,
    "settings":       _do_settings,
    "device_manager": _do_device_manager,
    "services":       _do_services,
    "registry":       _do_registry,
    "shell_folder":   _do_shell_folder,
}

# Aliases — multiple human phrasings map to one op key.
_ALIASES: dict[str, str] = {
    "lock computer":          "lock",
    "lock pc":                "lock",
    "lock workstation":       "lock",
    "sleep computer":         "sleep",
    "go to sleep":            "sleep",
    "standby":                "sleep",
    "log out":                "logoff",
    "logout":                 "logoff",
    "log off":                "logoff",
    "sign out":               "logoff",
    "shut down":              "shutdown",
    "shut down computer":     "shutdown",
    "shutdown computer":      "shutdown",
    "power off":              "shutdown",
    "restart computer":       "restart",
    "reboot":                 "restart",
    "open task manager":      "task_manager",
    "task manager":           "task_manager",
    "open control panel":     "control_panel",
    "control panel":          "control_panel",
    "open settings":          "settings",
    "settings app":           "settings",
    "windows settings":       "settings",
    "open device manager":    "device_manager",
    "device manager":         "device_manager",
    "open services":          "services",
    "services":               "services",
    "open registry editor":   "registry",
    "registry editor":        "registry",
    "open downloads":         "shell_folder:downloads",
    "downloads":              "shell_folder:downloads",
    "downloads folder":       "shell_folder:downloads",
    "open documents":         "shell_folder:documents",
    "documents":              "shell_folder:documents",
    "documents folder":       "shell_folder:documents",
    "open desktop":           "shell_folder:desktop",
    "desktop":                "shell_folder:desktop",
    "open recycle bin":       "shell_folder:recycle",
    "open recycle":           "shell_folder:recycle",
    "recycle bin":            "shell_folder:recycle",
}


def list_commands() -> list[str]:
    """Public list of canonical command keys (for testing / help)."""
    return list(_OPS.keys())


def resolve(phrase: str) -> Optional[str]:
    """Map a free-form phrase to a canonical op key. Returns None on miss."""
    if not phrase:
        return None
    key = phrase.strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    if key in _OPS:
        return key
    # fuzzy contains
    for k, v in _ALIASES.items():
        if k in key or key in k:
            return v
    return None


def execute(op_or_phrase: str, confirm_fn: Optional[Callable[[str], bool]] = None) -> dict:
    """Run a PC command. `op_or_phrase` may be a canonical op key, an alias,
    or a fuzzy phrase (e.g. "open downloads")."""
    if not op_or_phrase:
        return {"ok": False, "tts": "No command given, sir.", "op": ""}

    canonical = resolve(op_or_phrase)
    if not canonical:
        return {"ok": False,
                "tts": f"I don't know how to {op_or_phrase}, sir.",
                "op": op_or_phrase}

    # Decompose "shell_folder:downloads" -> handler + named arg.
    handler_args: dict = {"confirm_fn": confirm_fn}
    if canonical.startswith("shell_folder:"):
        handler_args["name"] = canonical.split(":", 1)[1]
        canonical = "shell_folder"

    handler = _OPS.get(canonical)
    if not handler:
        return {"ok": False,
                "tts": f"No handler for {canonical}, sir.",
                "op": canonical}

    logger.info("pc_control.execute: op=%s", canonical)
    try:
        return handler(handler_args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pc_control op failed: %s", canonical)
        return {"ok": False,
                "tts": f"PC command failed, sir. {exc}",
                "op": canonical}
