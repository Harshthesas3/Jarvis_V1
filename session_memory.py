"""
session_memory.py
-----------------
Maintains session context: current app, window, folder, file, clipboard,
search queries, and recent actions. Used by the planner for pronoun
resolution and context-aware routing.

Public API:
    get(key) -> str
    set(key, value) -> None
    push_action(action) -> None
    clear() -> None
    resolve_pronoun(text) -> str
    update_from_plan(plan) -> None

Implementation note
-------------------
This module is now a thin shim that reads/writes the unified
``context_store._STORE`` singleton.  All fields that previously lived in
``_SESSION`` have been migrated there so that task_executor, ui_core, and
session_memory all share a single authoritative context.
"""

from __future__ import annotations

import logging
import re

import context_store as _cs

logger = logging.getLogger("jarvis.session")

# ---------------------------------------------------------------------------
# Compatibility alias — the actual data lives in context_store._STORE.
# External code that imported ``_SESSION`` directly will get this reference.
# ---------------------------------------------------------------------------
_SESSION = _cs._STORE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get(key: str) -> str:
    return _cs.get(key)


def set(key: str, value: str) -> None:  # noqa: A001
    _cs.set(key, value)


def push_action(action: dict) -> None:
    _cs.push_action(action)


def clear() -> None:
    _cs.clear()


def resolve_pronoun(text: str) -> str:
    result = text
    if _cs.get("current_file"):
        result = result.replace("the file", _cs.get("current_file"))
    if _cs.get("current_folder"):
        result = result.replace("the folder", _cs.get("current_folder"))
    if _cs.get("current_app"):
        result = result.replace("the app", _cs.get("current_app"))
        result = result.replace("the application", _cs.get("current_app"))
    it_replacement = (
        _cs.get("current_file")
        or _cs.get("current_folder")
        or _cs.get("current_app")
    )
    if it_replacement:
        result = re.sub(r"\bit\b", it_replacement, result, flags=re.IGNORECASE)
    if _cs.get("last_search_query"):
        result = re.sub(r"\bthat\b", _cs.get("last_search_query"), result, flags=re.IGNORECASE)
    return result


def update_from_plan(plan: dict) -> None:
    action = plan.get("action", "")
    if action == "open_app" and plan.get("app"):
        _cs.set("current_app", plan["app"])
    elif action == "close_app" and plan.get("app"):
        if plan["app"].lower() in _cs.get("current_app").lower():
            _cs.set("current_app", "")
    elif action == "open_folder" and plan.get("path"):
        _cs.set("current_folder", plan["path"])
    elif action == "create_folder" and plan.get("name"):
        _cs.set("current_folder", plan["name"])
    elif action == "file_operation":
        op = plan.get("op", "")
        if op in ("create_file",) and plan.get("name"):
            _cs.set("current_file", plan["name"])
        elif op in ("open_file", "write_file", "append_file", "read_file") and plan.get("path"):
            _cs.set("current_file", plan["path"])
    elif action == "clipboard" and plan.get("op") == "write" and plan.get("text"):
        _cs.set("clipboard_contents", plan["text"])
    elif action == "web_search" and plan.get("query"):
        _cs.set("last_search_query", plan["query"])
    elif action == "browser_open" and plan.get("url"):
        _cs.set("current_browser_tab", plan["url"])
    push_action(plan)
