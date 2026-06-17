"""
context_engine.py
-----------------
Unified runtime context registry for JARVIS. Tracks the current state of
the environment — active application, focused window, last file/folder
touched, clipboard content, search results, and screenshot paths.

Serves as the single source of truth for pronoun resolution and context-aware
automation across planner, executor, and UI automation modules.

Public API:
    get(key: str) -> str
    set(key: str, value: str) -> None
    get_all() -> dict
    update_from_plan(plan: dict) -> None
    reset() -> None
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("jarvis.context")

_CONTEXT: dict = {
    "last_folder": "",
    "last_file": "",
    "last_clipboard": "",
    "last_search_result": "",
    "last_screenshot": "",
    "last_url": "",
    "current_app": "",
    "current_window": "",
    "current_file": "",
    "current_folder": "",
}


def get(key: str) -> str:
    return _CONTEXT.get(key, "")


def set(key: str, value: str) -> None:
    if key in _CONTEXT:
        _CONTEXT[key] = value


def get_all() -> dict:
    return dict(_CONTEXT)


def update_from_plan(plan: dict) -> None:
    action = plan.get("action", "")
    op = plan.get("op", "")
    folder = plan.get("folder", "")
    pname = plan.get("name", "")
    ppath = plan.get("path", "")

    if action == "folder_operation":
        if op == "create_folder":
            _CONTEXT["last_folder"] = pname
            _CONTEXT["current_folder"] = pname
        elif op == "rename_folder":
            new_name = plan.get("new_name", "")
            _CONTEXT["last_folder"] = new_name
            _CONTEXT["current_folder"] = new_name

    if action == "file_operation":
        if op == "create_file":
            _CONTEXT["last_file"] = pname
            _CONTEXT["current_file"] = pname
            if folder:
                _CONTEXT["current_folder"] = os.path.basename(folder.rstrip("/\\"))
        elif op in ("open_file", "write_file", "append_file", "read_file"):
            _CONTEXT["last_file"] = ppath
            _CONTEXT["current_file"] = ppath

    if action == "clipboard":
        if op == "write":
            _CONTEXT["last_clipboard"] = plan.get("text", "")
        elif op == "read":
            _CONTEXT["last_clipboard"] = plan.get("_result", "")

    if action == "screenshot":
        _CONTEXT["last_screenshot"] = plan.get("_result", "")

    if action == "web_search":
        _CONTEXT["last_search_result"] = plan.get("query", "")

    if action == "open_app":
        app = plan.get("app", "")
        _CONTEXT["last_app"] = app
        _CONTEXT["current_app"] = app

    if action == "browser_open":
        _CONTEXT["last_url"] = plan.get("url", "")

    if action in ("focus_window", "wait_for_window"):
        title = plan.get("title", "") or plan.get("target", "")
        if title:
            _CONTEXT["current_window"] = title

    if action == "search_in_app":
        app = plan.get("app", "")
        _CONTEXT["current_app"] = app
        _CONTEXT["current_window"] = app


def reset() -> None:
    for key in list(_CONTEXT.keys()):
        _CONTEXT[key] = ""
