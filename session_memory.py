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
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("jarvis.session")

_SESSION: dict = {
    "current_app": "",
    "current_window": "",
    "current_folder": "",
    "current_file": "",
    "current_browser_tab": "",
    "clipboard_contents": "",
    "last_search_query": "",
    "recent_actions": [],
}


def get(key: str) -> str:
    return _SESSION.get(key, "")


def set(key: str, value: str) -> None:
    if key in _SESSION:
        _SESSION[key] = value


def push_action(action: dict) -> None:
    _SESSION["recent_actions"].append(action)
    if len(_SESSION["recent_actions"]) > 20:
        _SESSION["recent_actions"].pop(0)


def clear() -> None:
    for k in _SESSION:
        if isinstance(_SESSION[k], list):
            _SESSION[k] = []
        else:
            _SESSION[k] = ""


def resolve_pronoun(text: str) -> str:
    result = text
    if _SESSION.get("current_file"):
        result = result.replace("the file", _SESSION["current_file"])
    if _SESSION.get("current_folder"):
        result = result.replace("the folder", _SESSION["current_folder"])
    if _SESSION.get("current_app"):
        result = result.replace("the app", _SESSION["current_app"])
        result = result.replace("the application", _SESSION["current_app"])
    it_replacement = (
        _SESSION.get("current_file")
        or _SESSION.get("current_folder")
        or _SESSION.get("current_app")
    )
    if it_replacement:
        result = re.sub(r"\bit\b", it_replacement, result, flags=re.IGNORECASE)
    if _SESSION.get("last_search_query"):
        result = re.sub(r"\bthat\b", _SESSION["last_search_query"], result, flags=re.IGNORECASE)
    return result


def update_from_plan(plan: dict) -> None:
    action = plan.get("action", "")
    if action == "open_app" and plan.get("app"):
        _SESSION["current_app"] = plan["app"]
    elif action == "close_app" and plan.get("app"):
        if plan["app"].lower() in _SESSION["current_app"].lower():
            _SESSION["current_app"] = ""
    elif action == "open_folder" and plan.get("path"):
        _SESSION["current_folder"] = plan["path"]
    elif action == "create_folder" and plan.get("name"):
        _SESSION["current_folder"] = plan["name"]
    elif action == "file_operation":
        op = plan.get("op", "")
        if op in ("create_file",) and plan.get("name"):
            _SESSION["current_file"] = plan["name"]
        elif op in ("open_file", "write_file", "append_file", "read_file") and plan.get("path"):
            _SESSION["current_file"] = plan["path"]
    elif action == "clipboard" and plan.get("op") == "write" and plan.get("text"):
        _SESSION["clipboard_contents"] = plan["text"]
    elif action == "web_search" and plan.get("query"):
        _SESSION["last_search_query"] = plan["query"]
    elif action == "browser_open" and plan.get("url"):
        _SESSION["current_browser_tab"] = plan["url"]
    push_action(plan)
