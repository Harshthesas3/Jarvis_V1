"""
context_store.py
----------------
Unified session context singleton for JARVIS.

All subsystems (task_executor, session_memory, ui_core) share a single dict
instead of maintaining their own separate copies.  This eliminates the stale-
state problem that arose from three independent stores diverging.

Structure
---------
The store is intentionally a plain dict so that existing callers that do
``ctx["key"] = value`` continue to work without any changes.

Keys
----
  current_app       str   — Name of the currently focused application
  current_window    str   — Title of the currently focused window
  current_folder    str   — Last-used folder path
  current_file      str   — Last-used file path
  current_browser_tab str — Current browser tab URL or title
  clipboard_contents str  — Last clipboard text written by JARVIS
  last_search_query  str  — Most recent web-search query
  last_search_result str  — Most recent web-search result text
  last_screenshot   str   — Path/description of last screenshot
  last_clipboard    str   — Alias kept for task_executor compatibility
  last_folder       str   — Alias kept for task_executor compatibility
  last_file         str   — Alias kept for task_executor compatibility
  last_app          str   — Alias kept for task_executor compatibility
  last_url          str   — Last opened URL
  recent_actions    list  — Ring-buffer of recent action dicts (max 20)
"""

from __future__ import annotations

import logging

logger = logging.getLogger("jarvis.context_store")

# ---------------------------------------------------------------------------
# Shared singleton — import this dict directly or use the helpers below
# ---------------------------------------------------------------------------
_STORE: dict = {
    # Primary context (used by session_memory + ui_core)
    "current_app":          "",
    "current_window":       "",
    "current_folder":       "",
    "current_file":         "",
    "current_browser_tab":  "",
    "clipboard_contents":   "",
    "last_search_query":    "",
    "recent_actions":       [],

    # Extended context (used by task_executor)
    "last_search_result":   "",
    "last_screenshot":      "",
    "last_clipboard":       "",
    "last_folder":          "",
    "last_file":            "",
    "last_app":             "",
    "last_url":             "",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get(key: str, default: str = "") -> str:
    """Return the value for *key*, falling back to *default*."""
    return _STORE.get(key, default)


def set(key: str, value) -> None:  # noqa: A001 – shadows builtin intentionally
    """Set *key* to *value*.  New keys are accepted (dynamic extension)."""
    if key not in _STORE:
        logger.debug("context_store: adding new key '%s'", key)
    _STORE[key] = value


def push_action(action: dict) -> None:
    """Append *action* to the recent_actions ring-buffer (max 20 entries)."""
    buf: list = _STORE["recent_actions"]
    buf.append(action)
    if len(buf) > 20:
        buf.pop(0)


def clear() -> None:
    """Reset all string fields to '' and clear recent_actions."""
    for k, v in _STORE.items():
        if isinstance(v, list):
            _STORE[k] = []
        else:
            _STORE[k] = ""


def snapshot() -> dict:
    """Return a shallow copy of the store (safe to serialise)."""
    snap = dict(_STORE)
    snap["recent_actions"] = list(_STORE["recent_actions"])
    return snap
