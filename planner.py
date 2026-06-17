"""
planner.py
----------
Intent → structured action plan.

Public API:
    plan_action(user_text: str) -> dict
    execute_plan(plan: dict) -> str
    register_tool(name: str, handler: callable) -> None
    SUPPORTED_ACTIONS: set[str]

Design notes:
- The planner prefers a deterministic regex fast-path for trivial commands
  (open, time, date, screenshot, volume, system control, clipboard, web search,
  websites, music, memory). This keeps latency low and works if Ollama is
  unavailable.
- For ambiguous / multi-step requests it calls Qwen 3.5:4b through Ollama with
  a strict system prompt and asks for a single JSON object.
- The JSON output is validated against an action whitelist. Unknown actions
  fall back to the AI chat handler.
- Plans can be single-action dicts OR {"steps": [...]} for multi-step work.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("jarvis.planner")

# ---------------------------------------------------------------------------
# Folder alias resolution
# ---------------------------------------------------------------------------
_KNOWN_ALIASES: dict[str, str] = {}


def register_folder_alias(name: str, path: str) -> None:
    _KNOWN_ALIASES[name.lower().strip()] = path


def _resolve_path(text: str) -> str:
    """Resolve folder aliases in a path string. Returns the resolved path."""
    if not text:
        return text
    result = text
    home = os.path.expanduser("~")
    alias_map = {
        "downloads": os.path.join(home, "Downloads"),
        "download": os.path.join(home, "Downloads"),
        "desktop": os.path.join(home, "Desktop"),
        "documents": os.path.join(home, "Documents"),
        "document": os.path.join(home, "Documents"),
        "pictures": os.path.join(home, "Pictures"),
        "music": os.path.join(home, "Music"),
        "videos": os.path.join(home, "Videos"),
        "home": home,
        "root": os.path.splitdrive(home)[0] + os.sep,
        "temp": os.environ.get("TEMP", os.path.join(home, "AppData", "Local", "Temp")),
    }
    def _replacer(alias: str, resolved: str) -> None:
        nonlocal result
        pattern = re.compile(
            r"(?<![\\/.\w])" + re.escape(alias) + r"(?![\\/.\w])",
            re.IGNORECASE,
        )
        result = pattern.sub(lambda m: resolved, result)

    for alias, resolved in alias_map.items():
        _replacer(alias, resolved)
    for alias, resolved in _KNOWN_ALIASES.items():
        _replacer(alias, resolved)
    return result


def _has_incomplete_params(plan: dict) -> bool:
    """Check if a plan is missing required parameters."""
    action = plan.get("action", "")
    if action == "file_operation":
        op = plan.get("op", "")
        if op in ("create_file",) and not plan.get("name"):
            return True
        if op in ("read_file", "delete_file", "open_file", "write_file", "append_file") and not plan.get("path"):
            return True
        if op in ("rename_file",) and (not plan.get("path") or not plan.get("new_name")):
            return True
        if op in ("move_file", "copy_file") and (not plan.get("path") or not plan.get("dest_folder")):
            return True
    if action == "folder_operation":
        op = plan.get("op", "")
        if op in ("create_folder",) and not plan.get("name"):
            return True
        if op in ("delete_folder", "list_folder") and not plan.get("path"):
            return True
    if action in ("web_search", "search_in_app", "search_in_app_v2", "type_text", "press_key") and not plan.get(action == "press_key" and "key" or "query" if action != "type_text" else "text"):
        return True
    return False


def _needs_clarification(text: str) -> dict | None:
    """Check if the user's request is incomplete and return a clarification
    prompt if so. Returns None if the request seems complete."""
    t = text.strip().lower()

    # Bare file creation
    if re.match(r"^(?:please\s+)?(?:create|make)\s+(?:a\s+|an\s+)?(?:file\s*)?(?:called\s+|named\s+)?\s*$", t):
        return {
            "action": "clarification",
            "question": "What should the file be named?",
            "hints": ["test.txt", "notes.txt", "main.py"],
        }

    # Bare folder creation
    if re.match(r"^(?:please\s+)?(?:create|make)\s+(?:a\s+|an\s+)?folder\s*$", t):
        return {
            "action": "clarification",
            "question": "What should the folder be named?",
            "hints": ["Python Projects", "Documents", "Test"],
        }

    # Bare reminder
    if re.match(r"^(?:please\s+)?(?:remind(?:\s+me)?|set\s+reminder|create\s+reminder)\s*$", t):
        return {
            "action": "clarification",
            "question": "What should I remind you about and when?",
            "hints": ["remind me in 5 minutes to check the oven", "remind me tomorrow at 9 am to buy groceries"],
        }

    # Bare search
    if re.match(r"^(?:please\s+)?(?:search|look\s+up|find)\s*$", t):
        return {
            "action": "clarification",
            "question": "What would you like me to search for?",
            "hints": ["search for Python tutorials", "search for weather in London"],
        }

    return None

SUPPORTED_ACTIONS: set[str] = {
    "open_app",
    "close_app",
    "switch_window",
    "focus_window",
    "web_search",
    "search_in_app",
    "search_in_app_v2",
    "reminder",
    "set_reminder",
    "calendar_event",
    "clipboard",
    "file_operation",
    "folder_operation",
    "pc_control",
    "email",
    "whatsapp",
    "screenshot",
    "screen_awareness",
    "system_control",
    "volume_control",
    "memory_store",
    "memory_recall",
    "memory_clear",
    "time",
    "date",
    "diagnostics",
    "system_stats",
    "music",
    "click",
    "double_click",
    "right_click",
    "move_mouse",
    "type_text",
    "press_key",
    "hotkey",
    "scroll",
    "browser_open",
    "browser_search",
    "browser_click",
    "run_program",
    "run_terminal_command",
    "generate_code",
    "wait",
    "wait_for_window",
    "wait_for_element",
    "ai_chat",
}

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
_TOOL_REGISTRY: Dict[str, Callable[[dict], str]] = {}


def register_tool(name: str, handler: Callable[[dict], str]) -> None:
    """Register a handler for an action name. Handler receives the plan dict
    and must return a short status string suitable for TTS."""
    if name not in SUPPORTED_ACTIONS:
        logger.warning("Registering tool for unknown action: %s", name)
    _TOOL_REGISTRY[name] = handler


def _dispatch(plan: dict) -> str:
    action = plan.get("action")
    handler = _TOOL_REGISTRY.get(action) if action else None
    if handler is None:
        return "I do not know how to do that yet, sir."
    try:
        return handler(plan)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Handler for %s failed", action)
        return f"Failed to execute {action}, sir. {exc}"


# ---------------------------------------------------------------------------
# Deterministic fast-path
# ---------------------------------------------------------------------------
_FAST_PATH_TRIGGERS: List[tuple] = [
    # ---------------------------------------------------------------
    # Close app — "close <app>" or "quit <app>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:close|quit|exit)\s+(?P<app>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "close_app", "app": m.group("app").strip()},
    ),
    # ---------------------------------------------------------------
    # Browser open — "open browser to <url>" or "go to <url>".
    # Must come BEFORE switch_window so URLs are not misrouted.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:open\s+browser\s+(?:to|at)\s+|go\s+to\s+)"
            r"(?P<url>https?://\S+|www\.\S+|\S+\.\w{2,}(?:/\S*)?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "browser_open", "url": m.group("url").strip()},
    ),
    # ---------------------------------------------------------------
    # Switch window — "switch to <window/app>". "go to" non-URLs
    # falls through to here.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:switch|go)\s+to\s+(?P<target>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "switch_window", "target": m.group("target").strip()},
    ),
    # ---------------------------------------------------------------
    # Open folder — "open folder <path>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?open\s+folder\s+(?P<path>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "open_folder", "path": m.group("path").strip()},
    ),
    # ---------------------------------------------------------------
    # Rename folder
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?rename\s+(?:the\s+)?folder\s+"
            r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<new_name>[\w.\- ]+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "rename_folder",
            "path": m.group("path").strip(),
            "new_name": m.group("new_name").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Append to file
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:append|add)\s+(?P<content>.+?)\s+to\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "append_file",
            "path": m.group("path").strip(),
            "content": m.group("content").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Search in app — "search for X in Y". Negative lookahead for
    # "files"/"the files" so those route to file_operation/search_files.
    # Routes to search_in_app_v2 (universal search engine).
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?search\s+(?:for\s+)?(?P<query>.+?)\s+in\s+(?!files?\s*$)(?P<app>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "search_in_app_v2",
            "query": _strip_query_punctuation(m.group("query")),
            "app": m.group("app").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Click — "click [at] (x, y)" or "click [button]"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?click\s+"
            r"(?:(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?)?"
            r"(?:\s*(?P<button>left|right|middle))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "click",
            "x": int(m.group("x")) if m.group("x") else None,
            "y": int(m.group("y")) if m.group("y") else None,
            "button": (m.group("button") or "left").lower(),
        },
    ),
    # ---------------------------------------------------------------
    # Double-click
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?double\s*click\s+"
            r"(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "double_click",
            "x": int(m.group("x")) if m.group("x") else None,
            "y": int(m.group("y")) if m.group("y") else None,
        },
    ),
    # ---------------------------------------------------------------
    # Right-click
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?right\s*click\s+"
            r"(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "right_click",
            "x": int(m.group("x")) if m.group("x") else None,
            "y": int(m.group("y")) if m.group("y") else None,
        },
    ),
    # ---------------------------------------------------------------
    # Type text — "type <text>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?type\s+(?P<text>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "type_text", "text": m.group("text").strip()},
    ),
    # ---------------------------------------------------------------
    # Press key — "press <key>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?press\s+(?P<key>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "press_key", "key": m.group("key").strip()},
    ),
    # ---------------------------------------------------------------
    # Scroll — "scroll up/down" or "scroll <n>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?scroll\s+"
            r"(?P<dir>up|down|left|right)?\s*"
            r"(?P<amount>\d+)?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "scroll",
            "direction": (m.group("dir") or "down").lower(),
            "amount": int(m.group("amount")) if m.group("amount") else 3,
        },
    ),
    # ---------------------------------------------------------------
    # Browser search — "search in browser for X"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?search\s+in\s+(?:the\s+)?browser\s+for\s+(?P<query>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "browser_search", "query": _strip_query_punctuation(m.group("query"))},
    ),
    # ---------------------------------------------------------------
    # Browser click — "click on <element> in browser"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?click\s+on\s+(?P<element>.+?)\s+in\s+(?:the\s+)?browser\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "browser_click",
            "element": m.group("element").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Diagnostics — "run diagnostics" or just "diagnostics"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:run\s+)?diagnostics\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "diagnostics"},
    ),
    # ---------------------------------------------------------------
    # Run program — "run <program>" (not "run command <...>").
    # Must come AFTER run_terminal_command to avoid stealing its input.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?run\s+(?!command\s)(?P<program>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "run_program", "program": m.group("program").strip()},
    ),
    # ---------------------------------------------------------------
    # Run terminal command — "run command <cmd>" or "execute <cmd>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:run\s+command|execute)\s+(?P<command>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "run_terminal_command",
            "command": m.group("command").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Generate code — "generate code for X" or "write code for X"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:generate|write)\s+code\s+(?:for|to)\s+(?P<description>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "generate_code",
            "description": m.group("description").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Wait — "wait <n> seconds" or "wait for <n> seconds"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?wait\s+(?:for\s+)?(?P<seconds>\d+)\s*"
            r"(?:seconds?|secs?)?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "wait", "seconds": int(m.group("seconds"))},
    ),
    # ---------------------------------------------------------------

    # ---------------------------------------------------------------
        # PC control: many phrases. `phrase` carries the user's words so
    # pc_control.resolve() can fuzzy-match the alias map.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?"
            r"(?P<phrase>"
            r"lock(?:\s+(?:the\s+)?(?:computer|pc|workstation))?"
            r"|put\s+(?:the\s+)?(?:computer|pc)\s+to\s+sleep"
            r"|sleep(?:\s+(?:the\s+)?(?:computer|pc|mode))?"
            r"|standby"
            r"|log\s*(?:out|off)"
            r"|sign\s+out"
            r"|shutdown(?:\s+(?:the\s+)?(?:computer|pc))?"
            r"|shut\s+down(?:\s+(?:the\s+)?(?:computer|pc))?"
            r"|power\s+off"
            r"|restart(?:\s+(?:the\s+)?(?:computer|pc))?"
            r"|reboot"
            r"|open\s+task\s+manager"
            r"|open\s+(?:the\s+)?control\s+panel"
            r"|open\s+(?:the\s+)?settings"
            r"|open\s+(?:the\s+)?device\s+manager"
            r"|open\s+services"
            r"|open\s+(?:the\s+)?registry(?:\s+editor)?"
            r"|open\s+downloads?(?:\s+folder)?"
            r"|open\s+documents?(?:\s+folder)?"
            r"|open\s+(?:my\s+)?desktop"
            r"|open\s+(?:the\s+)?recycle\s+bin"
            r"|open\s+(?:the\s+)?recycle"
            r")\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "pc_control",
            "phrase": m.group("phrase").strip().lower(),
        },
    ),
    # Standalone noun phrases that should also hit pc_control.
    (
        re.compile(
            r"^(?P<phrase>downloads?|downloads?\s+folder|"
            r"documents?|documents?\s+folder|"
            r"desktop|recycle\s+bin|recycle|"
            r"task\s+manager|control\s+panel|"
            r"device\s+manager|services|registry(?:\s+editor)?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "pc_control",
            "phrase": m.group("phrase").strip().lower(),
        },
    ),
    # ---------------------------------------------------------------
    # File open — "open file <path>" or "open <path.ext>". Must come
    # BEFORE the generic open_app pattern so extensions route correctly.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:open|launch|show)\s+(?:the\s+)?(?:file\s+)?(?P<path>[\w.\- /\\:]+?\.[a-zA-Z0-9]{1,5})$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "open_file",
            "path": m.group("path").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Clipboard read — "what's on my clipboard" etc. Must come BEFORE
    # the generic web_search "what is" pattern so clipboard queries
    # are not misrouted to the web.
    # ---------------------------------------------------------------
    (
        re.compile(r"^read\s+my\s+clipboard$|^what(?:'s|\s+is)\s+on\s+my\s+clipboard$",
                   re.IGNORECASE),
        lambda m, src: {"action": "clipboard", "op": "read"},
    ),
    (
        re.compile(r"^read\s+(?:the\s+)?clipboard$", re.IGNORECASE),
        lambda m, src: {"action": "clipboard", "op": "read"},
    ),
    (
        re.compile(r"^what(?:'s|\s+is)\s+on\s+(?:the\s+)?clipboard$",
                   re.IGNORECASE),
        lambda m, src: {"action": "clipboard", "op": "read"},
    ),
    (
        re.compile(r"^(?:summarize|explain)\s+(?:my\s+)?clipboard$",
                   re.IGNORECASE),
        lambda m, src: {"action": "clipboard", "op": "summarize"},
    ),
    (
        re.compile(
            r"^(?:copy|put|write)\s+(?P<text>.+?)\s+(?:to|on)\s+(?:my\s+)?clipboard$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "clipboard", "op": "write", "text": m.group("text").strip()},
    ),
    # ---------------------------------------------------------------
    # Time / date — must come BEFORE the web_search "what is" pattern.
    # ---------------------------------------------------------------
    (
        re.compile(r"^what(?:'s|\s+is)\s+the\s+time(?:\s+now)?$", re.IGNORECASE),
        lambda m, src: {"action": "time"},
    ),
    (
        re.compile(r"^what\s+time\s+is\s+it(?:\s+now)?$", re.IGNORECASE),
        lambda m, src: {"action": "time"},
    ),
    (
        re.compile(r"^what(?:'s|\s+is)\s+(?:the\s+)?(?:today(?:'s)?\s+)?date$", re.IGNORECASE),
        lambda m, src: {"action": "date"},
    ),
    (
        re.compile(r"^what\s+(?:day|date)\s+is\s+(?:it|today)$", re.IGNORECASE),
        lambda m, src: {"action": "date"},
    ),
    (
        re.compile(r"^(?:battery|cpu|ram|memory(?:\s+usage)?|system\s+stats?)$",
                   re.IGNORECASE),
        lambda m, src: {"action": "system_stats", "metric": m.group(0).lower()},
    ),
    # ---------------------------------------------------------------
    # File search — "search for X in files". Must come BEFORE the
    # generic web_search "search for X" pattern.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?search\s+(?:for\s+)?files?\s+"
            r"(?:containing|matching|named)\s+(?P<query>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "search_files",
            "query": m.group("query").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?search\s+(?:for\s+)?(?P<query>.+?)\s+"
            r"(?:in\s+files?|across\s+files?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "search_files",
            "query": m.group("query").strip(),
        },
    ),
    # "open <anything>" — single-app launch.
    # Accepts multi-word app names ("open visual studio code",
    # "open android studio", "open google chrome") but bails out
    # if a conjunction / second verb follows, so the LLM planner
    # can build a proper {"steps": [...]} plan instead.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^open\s+(?P<app>[a-zA-Z][\w\s.\-]*?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: (
            None
            if re.search(
                r"\b(?:and|then|after\s+that|also|plus)\b",
                m.group("app"), re.IGNORECASE,
            )
            else {"action": "open_app", "app": m.group("app").strip()}
        ),
    ),
    # "launch <app>" / "start <app>" / "run <app>"
    (
        re.compile(
            r"^(?:launch|start|run)\s+(?P<app>[a-zA-Z][\w\s.\-]*?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: (
            None
            if re.search(
                r"\b(?:and|then|after\s+that|also|plus)\b",
                m.group("app"), re.IGNORECASE,
            )
            else {"action": "open_app", "app": m.group("app").strip()}
        ),
    ),
    (
        re.compile(
            r"^(?:remind\s+me\s+)?(?:at|on)?\s*"
            r"(?P<time>tomorrow\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|"
            r"today\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|"
            r"\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
            r"tomorrow|tonight|tonight\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+"
            r"to\s+(?P<task>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "reminder",
            "time": m.group("time").strip(),
            "task": m.group("task").strip(),
        },
    ),
    (
        re.compile(
            r"^remind\s+me\s+(?P<time>.+?)\s+to\s+(?P<task>.+)$", re.IGNORECASE
        ),
        lambda m, src: {
            "action": "reminder",
            "time": m.group("time").strip(),
            "task": m.group("task").strip(),
        },
    ),
    (
        re.compile(r"^show\s+reminders?$|^list\s+reminders?$", re.IGNORECASE),
        lambda m, src: {"action": "reminder", "op": "list"},
    ),
    (
        re.compile(r"^clear\s+reminders?$", re.IGNORECASE),
        lambda m, src: {"action": "reminder", "op": "clear"},
    ),
    (
        re.compile(
            r"^(?:delete|remove)\s+reminder\s+(?P<idx>\d+)$", re.IGNORECASE
        ),
        lambda m, src: {
            "action": "reminder",
            "op": "remove",
            "index": int(m.group("idx")),
        },
    ),
    (
        re.compile(
            r"^(?:create|add|schedule)\s+(?:a\s+)?"
            r"(?P<title>.+?)\s+(?P<date>tomorrow|today|monday|tuesday|"
            r"wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:st|nd|rd|th)?"
            r"\s+\w+|\d{4}-\d{2}-\d{2})\s+at\s+"
            r"(?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm))$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "calendar_event",
            "title": m.group("title").strip(),
            "date": m.group("date").strip(),
            "time": m.group("time").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:message|whatsapp|send\s+whatsapp(?:\s+message)?\s+to)\s+"
            r"(?P<contact>[a-zA-Z][\w\s]{0,40}?)\s+"
            r"(?:that\s+)?(?P<message>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "whatsapp",
            "contact": m.group("contact").strip(),
            "message": m.group("message").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:tell|message)\s+(?P<contact>mom|dad|brother|sister|"
            r"friend|bhajan|[a-zA-Z][\w]{0,30})\s+"
            r"(?:that\s+)?(?P<message>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "whatsapp",
            "contact": m.group("contact").strip(),
            "message": m.group("message").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:email|draft\s+(?:an\s+)?email(?:\s+to)?)\s+"
            r"(?P<recipient>[a-zA-Z][\w\s]{0,40}?)\s+"
            r"(?:about|with|re:)?\s*(?P<subject>.+?)\s+"
            r"saying\s+(?P<body>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "email",
            "recipient": m.group("recipient").strip(),
            "subject": m.group("subject").strip(),
            "body": m.group("body").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:email|draft\s+(?:an\s+)?email(?:\s+to)?)\s+"
            r"(?P<recipient>[a-zA-Z][\w\s]{0,40}?)\s+"
            r"(?:about|with|re:)?\s*(?P<subject>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "email",
            "recipient": m.group("recipient").strip(),
            "subject": m.group("subject").strip(),
            "body": "",
        },
    ),
    # ---------------------------------------------------------------
    # Screen awareness — capture + analyze a screenshot via the
    # configured vision model. A few common phrasings get the fast
    # path; the LLM planner picks up the rest (e.g. "summarize this
    # page", "help me fix this"). Defined BEFORE the web_search /
    # "what is" patterns so phrases like "what's on my screen" route
    # to vision rather than DuckDuckGo.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^what(?:'s|\s+is)\s+on\s+my\s+screen$|^read\s+my\s+screen$|"
            r"^describe\s+(?:my\s+)?screen$|^describe\s+this\s+page$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "screen_awareness",
            "op": "describe",
        },
    ),
    (
        re.compile(
            r"^(?:analyze|explain)\s+this\s+error$|"
            r"^what\s+error(?:\s+is\s+(?:this|shown))?$|"
            r"^help\s+me\s+(?:fix|solve)\s+this(?:\s+error)?$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "screen_awareness",
            "op": "error",
        },
    ),
    (
        re.compile(
            r"^(?:explain|review)\s+this\s+code$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "screen_awareness",
            "op": "code_review",
        },
    ),
    (
        re.compile(
            r"^(?:read|summarize)\s+this\s+(?:page|document)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "screen_awareness",
            "op": "summarize_document",
        },
    ),
    (
        re.compile(
            r"^(?:search(?:\s+the\s+web)?(?:\s+for)?|look\s+up|"
            r"ask\s+the\s+web|tell\s+me\s+about)\s+(?P<query>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: (
            None
            if re.search(
                r"\b(?:and|then|after\s+that|also|plus)\s+"
                r"(?:save|open|create|send|remind|search|launch|start)\b",
                m.group("query"), re.IGNORECASE,
            )
            else {"action": "web_search", "query": _strip_query_punctuation(m.group("query"))}
        ),
    ),
    (
        re.compile(
            r"^(?:what\s+is|who\s+is|whats|what's)\s+(?P<query>.+?)\??$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "web_search",
            "query": _strip_query_punctuation(m.group("query")),
        },
    ),
    (
        re.compile(r"^remember\s+that\s+(?P<fact>.+)$", re.IGNORECASE),
        lambda m, src: {"action": "memory_store", "fact": m.group("fact").strip()},
    ),
    (
        re.compile(r"^remember\s+(?P<fact>.+)$", re.IGNORECASE),
        lambda m, src: {"action": "memory_store", "fact": m.group("fact").strip()},
    ),
    (
        re.compile(
            r"^what\s+do\s+you\s+remember$|^recall(?:\s+memory)?$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "memory_recall"},
    ),
    (
        re.compile(
            r"^forget\s+everything$|^clear\s+(?:your\s+)?memory$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "memory_clear"},
    ),

    (
        re.compile(r"^(?:screenshot|take\s+a\s+screenshot|capture\s+screen)$",
                   re.IGNORECASE),
        lambda m, src: {"action": "screenshot"},
    ),

    (
        re.compile(
            r"^volume\s+(?P<dir>up|down|mute|unmute)$", re.IGNORECASE
        ),
        lambda m, src: {"action": "volume_control", "op": m.group("dir").lower()},
    ),
    (
        re.compile(
            r"^set\s+volume\s+to\s+(?P<level>\d+)\s*(?:percent)?%?$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "volume_control",
            "op": "set",
            "level": int(m.group("level")),
        },
    ),
    (
        re.compile(
            r"^(?P<op>play|pause|stop|next|previous|skip)\s+(?:music|song|track)$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "music", "op": m.group("op").lower()},
    ),
    (
        re.compile(
            r"^(?:lock(?:\s+computer)?|shutdown(?:\s+computer)?|"
            r"restart(?:\s+computer)?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "system_control", "op": m.group(0).lower().split()[0]},
    ),
    # ---------------------------------------------------------------
    # Clipboard: clear (the read/summarize/write patterns are above).
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:clear|empty|wipe)\s+(?:my\s+)?clipboard$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "clipboard", "op": "clear"},
    ),
    # ---------------------------------------------------------------
    # Create file — "create <name>" or "create a file called <name>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?create\s+(?:a\s+|an\s+)?(?:file\s+)?"
            r"(?:called\s+|named\s+)?(?P<name>[\w.\- ]+?\.\w+)"
            r"(?:\s+(?:in|inside|under)\s+(?P<folder>.+?))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: _build_create_file(m),
    ),
    (
        re.compile(
            r"^(?:please\s+)?make\s+(?:a\s+|an\s+)?(?:file\s+)?"
            r"(?:called\s+|named\s+)?(?P<name>[\w.\- ]+?\.\w+)"
            r"(?:\s+(?:in|inside|under)\s+(?P<folder>.+?))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: _build_create_file(m),
    ),
    (
        re.compile(
            r"^(?:please\s+)?create\s+(?:a\s+|an\s+)?(?:file\s+)?"
            r"(?:called\s+|named\s+)?(?P<name>[\w.\- ]+?\.\w+)"
            r"\s+(?:with|containing)\s+(?P<content>.+)"
            r"(?:\s+(?:in|inside|under)\s+(?P<folder>.+?))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: _build_create_file_with_content(m),
    ),
    # "write a <lang> program that <task>" -> code generation
    (
        re.compile(
            r"^(?:please\s+)?(?:write|create|make)\s+(?:a\s+|an\s+)?"
            r"(?P<name>[\w.\- ]+?\.\w+)"
            r"\s+(?:with|that)\s+(?P<content>.+?)(?:\s+(?:in|inside|under)\s+(?P<folder>.+?))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: _build_codegen_from_file(m, src),
    ),
    # ---------------------------------------------------------------

    (
        re.compile(
            r"^(?:please\s+)?read\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "read_file",
            "path": _strip_file_name(m.group("path")),
        },
    ),

    (
        re.compile(
            r"^(?:please\s+)?delete\s+(?:the\s+)?(?:file\s+)?(?P<path>(?!folder\b)(?!the\s+folder\b).+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "delete_file",
            "path": _strip_file_name(m.group("path")),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?rename\s+(?:the\s+)?(?:file\s+)?"
            r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<new_name>[\w.\- ]+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "rename_file",
            "path": _strip_file_name(m.group("path")),
            "new_name": _strip_file_name(m.group("new_name")),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?move\s+(?:the\s+)?(?:file\s+)?"
            r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<dest>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "move_file",
            "path": _strip_file_name(m.group("path")),
            "dest_folder": m.group("dest").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?copy\s+(?:the\s+)?(?:file\s+)?"
            r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<dest>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "copy_file",
            "path": _strip_file_name(m.group("path")),
            "dest_folder": m.group("dest").strip(),
        },
    ),

    # "write <content> into <path>" — used with pronoun resolution
    (
        re.compile(
            r"^(?:please\s+)?write\s+(?P<content>.+?)\s+into\s+(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "write_file",
            "path": _strip_file_name(m.group("path")),
            "content": m.group("content").strip(),
        },
    ),
    # "write <content> to <path>" — alternative phrasing
    (
        re.compile(
            r"^(?:please\s+)?write\s+(?P<content>.+?)\s+to\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "write_file",
            "path": _strip_file_name(m.group("path")),
            "content": m.group("content").strip(),
        },
    ),
    # "write <content> in(to) <path>" — broader match
    (
        re.compile(
            r"^(?:please\s+)?(?:write|put|add)\s+(?P<content>.+?)\s+"
            r"(?:in|into|inside|to)\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "write_file",
            "path": _strip_file_name(m.group("path")),
            "content": m.group("content").strip(),
        },
    ),

    # ---------------------------------------------------------------
    # Folder operations
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?create\s+(?:a\s+|an\s+)?folder\s+(?:called\s+|named\s+)?(?P<name>[\w.\- ]+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "create_folder",
            "name": m.group("name").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?delete\s+(?:the\s+)?folder\s+(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "delete_folder",
            "path": m.group("path").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?list\s+(?:the\s+)?(?P<path>.+?)\s+folder$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "list_folder",
            "path": m.group("path").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?list\s+(?:my\s+|the\s+)?(?P<path>downloads?|documents?|desktop|home|pictures|videos|music)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "list_folder",
            "path": m.group("path").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Focus window — "focus <window>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?focus\s+(?:on\s+)?(?:the\s+)?(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "focus_window", "title": m.group("title").strip()},
    ),
    # ---------------------------------------------------------------
    # Wait for window — "wait for <window>" or "wait for <n> seconds"
    # Must come after the generic "wait <n> seconds" pattern (line ~450).
    # This pattern matches non-numeric targets so it won't steal seconds.
    # ---------------------------------------------------------------
    (
        # This is intentionally after wait <seconds>; this catches
        # non-numeric "wait for <window>" phrases.
        re.compile(
            r"^(?:please\s+)?wait\s+for\s+(?:the\s+)?(?P<title>(?!\d+)\D.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "wait_for_window",
            "title": m.group("title").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Hotkey — "press ctrl+s", "press ctrl shift f", "press ctrl+l"
    # Must come AFTER the generic "press <key>" pattern.
    # We detect multi-key combos (2+ words).
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:press|hit)\s+"
            r"(?P<keys>(?:ctrl|alt|shift|win|cmd|meta)[\s+]+[a-z0-9]+)"
            r"(?:\s+(?:and\s+)?(?:then\s+)?(?:press\s+)?(?P<key2>[a-z0-9]+))?"
            r"\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "hotkey",
            "keys": re.split(r"\s*[\s+]\s*", m.group("keys").strip().lower()),
        },
    ),
]


def _build_create_file(m: re.Match) -> dict:
    name = _strip_file_name(m.group("name"))
    folder = m.group("folder").strip() if m.group("folder") else ""
    plan = {"action": "file_operation", "op": "create_file", "name": name}
    if folder:
        plan["folder"] = _resolve_path(folder)
    return plan


def _build_create_file_with_content(m: re.Match) -> dict:
    name = _strip_file_name(m.group("name"))
    content = m.group("content").strip()
    folder = m.group("folder").strip() if m.group("folder") else ""
    plan = {"action": "file_operation", "op": "create_file", "name": name, "content": content}
    if folder:
        plan["folder"] = _resolve_path(folder)
    return plan


def _build_codegen_from_file(m: re.Match, src: str) -> dict:
    name = _strip_file_name(m.group("name"))
    content = m.group("content").strip()
    folder = m.group("folder").strip() if m.group("folder") else ""
    ext = os.path.splitext(name)[1].lower()
    lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                 ".cpp": "cpp", ".c": "c", ".java": "java", ".go": "go",
                 ".rs": "rust", ".rb": "ruby", ".php": "php", ".swift": "swift",
                 ".kt": "kotlin", ".sh": "bash", ".bat": "batch", ".ps1": "powershell",
                 ".html": "html", ".css": "css", ".json": "json", ".yaml": "yaml",
                 ".xml": "xml", ".sql": "sql", ".r": "r", ".lua": "lua",
                 ".pl": "perl", ".hs": "haskell", ".ex": "elixir"}
    language = lang_map.get(ext, "")
    steps = [
        {"action": "file_operation", "op": "create_file", "name": name},
        {"action": "generate_code", "description": content, "language": language, "target_file": name},
    ]
    if folder:
        resolved = _resolve_path(folder)
        steps[0]["folder"] = resolved
    return {"steps": steps}


_TRAILING_PUNCTUATION_RE = re.compile(r"[.,!?;:]+$")


def _strip_query_punctuation(query: str) -> str:
    """Remove trailing punctuation from a search query."""
    return _TRAILING_PUNCTUATION_RE.sub("", query).strip()


def _strip_file_name(name: str) -> str:
    """Strip trailing punctuation from a file name (but preserve extension)."""
    name = name.strip()
    # Strip trailing punctuation that isn't part of the extension
    if "." in name:
        base, ext = name.rsplit(".", 1)
        base = _TRAILING_PUNCTUATION_RE.sub("", base).strip()
        ext = _TRAILING_PUNCTUATION_RE.sub("", ext).strip()
        if ext:
            return f"{base}.{ext}"
    return _TRAILING_PUNCTUATION_RE.sub("", name).strip()


def _try_fast_path(user_text: str) -> Optional[dict]:
    src = user_text.strip()
    for pattern, builder in _FAST_PATH_TRIGGERS:
        m = pattern.match(src)
        if m:
            return builder(m, src)
    return None


# ---------------------------------------------------------------------------
# Multi-step infrastructure
# ---------------------------------------------------------------------------
# Context for pronoun resolution within a single plan_action call.
_INITIAL_CONTEXT: dict = {
    "last_folder": "",
    "last_file": "",
    "last_clipboard": "",
    "last_search_result": "",
    "last_screenshot": "",
    "current_file": "",
    "current_folder": "",
    "current_app": "",
    "current_window": "",
}

_MULTI_STEP_DETECT_RE = re.compile(
    r"[,;]"
    r"|\b(?:and\s+then|then\s+after\s+that|after\s+that|next|also|finally|followed\s+by|plus)\b"
    r"|\b(?:and|then)\b\s*"
    r"(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make"
    r"|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause"
    r"|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze"
    r"|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell"
    r"|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press"
    r"|scroll|click|double|right|run|execute|generate|wait))",
    re.IGNORECASE,
)


def _has_multi_step_intent(text: str) -> bool:
    return bool(_MULTI_STEP_DETECT_RE.search(text))


def _split_clauses(text: str) -> list[str]:
    DELIM = "\x00"

    _VERB_PREFIX = (
        r"(?:please\s+)?"
        r"(?:open|launch|start|run|close|quit|exit|switch|go|create|make|"
        r"read|write|append|add|delete|rename|move|copy|search|remind|set|"
        r"play|pause|stop|next|previous|skip|lock|shutdown|restart|take|"
        r"capture|describe|analyze|explain|summarize|remember|recall|forget|"
        r"clear|show|list|add|schedule|tell|message|email|draft|send|volume|"
        r"save|put|log|sign|power|reboot|type|press|scroll|click|double|"
        r"right|run|execute|generate|wait)"
    )

    def _split_on_boundary_words(t: str) -> list[str]:
        for pat in [
            r"\band\s+then\b",
            r"\bthen\s+after\s+that\b",
            r"\bafter\s+that\b",
            r"\bnext\b",
            r"\balso\b",
            r"\bfinally\b",
            r"\bfollowed\s+by\b",
            r"\bplus\b",
        ]:
            t = re.sub(pat, DELIM, t, flags=re.IGNORECASE)
        for pat in [
            r"\band\b(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press|scroll|click|double|right|run|execute|generate|wait))",
            r"\bthen\b(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press|scroll|click|double|right|run|execute|generate|wait))",
        ]:
            t = re.sub(pat, DELIM, t, flags=re.IGNORECASE)
        return [c.strip() for c in t.split(DELIM) if c.strip()]

    # Phase 1: split on commas / semicolons, but only if the part after
    # the comma looks like a standalone command (starts with a verb).
    raw_parts = re.split(r"\s*[,;]\s*", text)
    parts: list[str] = []
    for i, part in enumerate(raw_parts):
        if i == 0:
            parts.append(part)
        else:
            # Check if this part starts like a command
            if re.match(_VERB_PREFIX, part.strip(), re.IGNORECASE):
                parts.append(part)
            else:
                # Not a command — merge with previous part
                parts[-1] = parts[-1] + ", " + part
    # Phase 2: split each part on boundary words
    result: list[str] = []
    for part in parts:
        result.extend(_split_on_boundary_words(part))
    # Phase 3: clean leading boundary words from each clause
    cleaned: list[str] = []
    for clause in result:
        c = re.sub(
            r"^(?:\s*(?:and\s+then|then\s+after\s+that|after\s+that|then|and|also|finally|next|plus)\s+)+",
            "", clause, flags=re.IGNORECASE,
        ).strip()
        if c:
            cleaned.append(c)
    return cleaned


def _resolve_pronouns(text: str, ctx: dict) -> str:
    result = text
    # Resolve "it" to the most recently created / opened file or folder
    file_ref = ctx.get("current_file") or ctx.get("last_file", "")
    folder_ref = ctx.get("current_folder") or ctx.get("last_folder", "")
    if file_ref or folder_ref:
        if folder_ref and file_ref and "/" not in file_ref and "\\" not in file_ref:
            replacement = folder_ref + "/" + file_ref
        else:
            replacement = file_ref or folder_ref
        result = re.sub(r"\bit\b", replacement, result, flags=re.IGNORECASE)
    # Resolve "there" to the current folder
    if folder_ref:
        result = re.sub(r"\bthere\b", folder_ref, result, flags=re.IGNORECASE)
    this_val = ctx.get("last_clipboard") or ctx.get("last_screenshot") or ""
    if this_val:
        result = re.sub(r"\bthis\b", this_val, result, flags=re.IGNORECASE)
    if ctx.get("last_search_result"):
        result = re.sub(r"\bthat\b", ctx["last_search_result"], result, flags=re.IGNORECASE)
    return result


def _update_context_from_plan(ctx: dict, plan: dict) -> None:
    action = plan.get("action", "")
    op = plan.get("op", "")
    folder = plan.get("folder", "")
    if action == "folder_operation":
        if op == "create_folder":
            name = plan.get("name", "")
            ctx["last_folder"] = name
            ctx["current_folder"] = name
        elif op == "rename_folder":
            ctx["last_folder"] = plan.get("new_name", "")
            ctx["current_folder"] = plan.get("new_name", "")
    if action == "file_operation":
        pname = plan.get("name", "")
        ppath = plan.get("path", "")
        if op == "create_file":
            ctx["last_file"] = pname
            ctx["current_file"] = pname
            if folder:
                ctx["current_folder"] = os.path.basename(folder.rstrip("/\\"))
        elif op in ("open_file", "write_file", "append_file", "read_file"):
            ctx["last_file"] = ppath
            ctx["current_file"] = ppath
    if action == "clipboard" and op == "write":
        ctx["last_clipboard"] = plan.get("text", "")
    if action == "open_app":
        ctx["last_app"] = plan.get("app", "")
        ctx["current_app"] = plan.get("app", "")
    if action == "web_search":
        ctx["last_search_result"] = plan.get("query", "")
    if action in ("focus_window", "wait_for_window"):
        title = plan.get("title", "") or plan.get("target", "")
        if title:
            ctx["current_window"] = title
    if action in ("search_in_app", "search_in_app_v2"):
        ctx["current_app"] = plan.get("app", "")
        ctx["current_window"] = plan.get("app", "")


def _plan_single(text: str, use_llm: bool = True) -> dict:
    fast = _try_fast_path(text)
    if fast is not None:
        # Normalize "run <app>" → open_app when program looks like an app name
        if fast.get("action") == "run_program":
            program = fast.get("program", "")
            if (program and re.match(r"^[a-zA-Z][\w\s.\-]*$", program)
                    and "." not in program
                    and "/" not in program and "\\" not in program):
                return {"action": "open_app", "app": program}
        return fast
    if not use_llm:
        return {"action": "ai_chat", "text": text}
    raw = _call_planner_llm(text)
    parsed = _extract_json(raw) if raw else None
    validated = _validate_plan(parsed) if parsed else None
    if validated is not None:
        return validated
    return {"action": "ai_chat", "text": text}


# ---------------------------------------------------------------------------
# LLM-based planner
# ---------------------------------------------------------------------------
_PLANNER_SYSTEM_PROMPT = """You are JARVIS, Harshith's personal AI planner.
You translate spoken requests into a strict JSON plan that another module
will execute.

Rules:
- Output a SINGLE JSON object. No prose, no markdown, no comments.
- The JSON must be either:
    {"action": "<name>", ...parameters}
  OR for multi-step:
    {"steps": [{"action": "<name>", ...}, ...]}
- Allowed actions:
  open_app, close_app, switch_window, focus_window, web_search, search_in_app, search_in_app_v2,
  reminder, set_reminder, calendar_event, clipboard, email,
  whatsapp, screenshot, screen_awareness, system_control, volume_control,
  memory_store, memory_recall, memory_clear, time, date, diagnostics, system_stats,
  music, ai_chat, file_operation, folder_operation, pc_control,
  click, double_click, right_click, move_mouse, type_text, press_key,
  hotkey, scroll, browser_open, browser_search, browser_click,
  run_program, run_terminal_command, generate_code, wait,
  wait_for_window, wait_for_element.
- For file ops: {"action":"file_operation","op":"<op>","name|path|query|dest_folder|new_name|content":...}
  where op is one of: create_file, read_file, write_file, append_file,
  delete_file, rename_file, move_file, copy_file, search_files, open_file.
- For folder ops: {"action":"folder_operation","op":"<op>","name|path":...}
  where op is one of: create_folder, delete_folder, rename_folder, list_folder.
- For PC control: {"action":"pc_control","phrase":"<user words>"}
  e.g. "lock computer", "open downloads", "shutdown", "restart".
- For mouse: {"action":"click", "x":int|None, "y":int|None, "button":"left|right|middle"}
- For keyboard: {"action":"type_text","text":"..."} or {"action":"press_key","key":"..."}
- For scroll: {"action":"scroll","direction":"up|down|left|right","amount":int}
- For browser: {"action":"browser_open","url":"..."} or {"action":"browser_search","query":"..."}
- For code: {"action":"generate_code","description":"...","language":"..."} (language is optional)
- For commands: {"action":"run_terminal_command","command":"..."} or {"action":"run_program","program":"..."}
- For waiting: {"action":"wait","seconds":int}
- For close_app: {"action":"close_app","app":"<app name>"}
- For switch_window: {"action":"switch_window","target":"<window name>"}
- For app search: {"action":"search_in_app","query":"...","app":"..."}
- For reminders: {"action":"reminder","time":"<when>","task":"<what>"}.
- For calendar: {"action":"calendar_event","title":"...","date":"...","time":"..."}.
- For WhatsApp: {"action":"whatsapp","contact":"...","message":"..."}.
- For email: {"action":"email","recipient":"...","subject":"...","body":"..."}.
- For focusing: {"action":"focus_window","title":"<window title>"}.
- For hotkeys: {"action":"hotkey","keys":["key1","key2",...]} e.g. {"action":"hotkey","keys":["ctrl","l"]}.
- For mouse move: {"action":"move_mouse","x":int,"y":int}.
- For wait_for_window: {"action":"wait_for_window","title":"<window title>","timeout":15}.
- For wait_for_element: {"action":"wait_for_element","automation_id":"<id>"} or {"text":"<text>"}.
- For opening apps: {"action":"open_app","app":"<app name>"}.
- For multi-step: chain actions in order, e.g. "open calculator then type 5+5"
  -> {"steps":[{"action":"open_app","app":"calculator"},{"action":"type_text","text":"5+5"}]}.
- Keep the JSON minimal. Do not invent parameters the user did not supply.

CRITICAL: Only use {"action":"ai_chat","text":"..."} as a LAST RESORT when the
user's request is purely conversational (greetings, opinions, jokes, chitchat,
general knowledge questions). For EVERYTHING ELSE — any request that involves
creating, opening, searching, browsing, controlling, remembering, or
manipulating something — pick a real action. If you cannot map the request
to an exact action, prefer web_search or memory_recall over ai_chat.
"""


def _call_planner_llm(user_text: str) -> Optional[str]:
    """Call Ollama with the planning prompt. Returns the raw text or None."""
    try:
        import ollama  # local import: keeps planner importable in tests
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ollama import failed: %s", exc)
        return None

    try:
        resp = ollama.chat(
            model="qwen3.5:4b",
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            options={"temperature": 0.0, "num_predict": 400},
        )
        return resp["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Planner LLM call failed: %s", exc)
        return None


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of `text` and parse it. Returns None
    if no valid JSON is found."""
    if not text:
        return None
    match = _JSON_OBJECT_RE.search(text)
    candidate = match.group(0) if match else text.strip()
    # Try strict first, then a light repair.
    for attempt in (candidate, _light_json_repair(candidate)):
        try:
            return json.loads(attempt)
        except Exception:  # noqa: BLE001
            continue
    return None


def _light_json_repair(text: str) -> str:
    """Common small fixes: trailing commas, single quotes, smart quotes."""
    out = text
    out = re.sub(r",\s*([}\]])", r"\1", out)  # trailing commas
    out = out.replace("“", '"').replace("”", '"')
    out = out.replace("‘", "'").replace("’", "'")
    # Replace single-quoted strings with double-quoted (very conservative).
    out = re.sub(r"'([^'\n]+)'\s*:", r'"\1":', out)
    out = re.sub(r":\s*'([^'\n]+)'", r': "\1"', out)
    return out


def _validate_plan(plan: dict) -> Optional[dict]:
    """Coerce / validate the plan shape. Returns the cleaned plan or None."""
    if not isinstance(plan, dict):
        return None

    if "steps" in plan:
        steps = plan["steps"]
        if not isinstance(steps, list) or not steps:
            return None
        cleaned_steps: List[dict] = []
        for step in steps:
            if not isinstance(step, dict):
                return None
            action = step.get("action")
            if action not in SUPPORTED_ACTIONS:
                return None
            cleaned_steps.append(step)
        return {"steps": cleaned_steps}

    action = plan.get("action")
    if action not in SUPPORTED_ACTIONS:
        return None
    return plan


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def plan_action(user_text: str, *, use_llm: bool = True) -> dict:
    """Convert a natural-language request into a structured plan.

    Returns either a single-action dict {"action": ..., ...} or
    {"steps": [...]} for multi-step plans. Falls back to
    {"action": "ai_chat", "text": user_text} when nothing else fits.
    Also supports {"action": "clarification", "question": ...} for
    incomplete commands.
    """
    if not user_text or not user_text.strip():
        return {"action": "ai_chat", "text": ""}

    text = user_text.strip()

    # Apply speech correction
    try:
        import speech_correction
        corrected = speech_correction.correct(text)
        if corrected != text:
            logger.info("Speech correction: '%s' -> '%s'", text, corrected)
        text = corrected
    except ImportError:
        pass

    # Check for incomplete commands (clarification handler)
    clarification = _needs_clarification(text)
    if clarification is not None:
        logger.info("Clarification needed: %s", clarification["question"])
        return clarification

    # Multi-step path: detect boundaries and split into clauses
    if _has_multi_step_intent(text):
        clauses = _split_clauses(text)
        if len(clauses) > 1:
            local_ctx = dict(_INITIAL_CONTEXT)
            # Load current_app from session memory (Issue 7)
            try:
                import session_memory as _sm
                ctx_app = _sm.get("current_app")
                if ctx_app:
                    local_ctx["current_app"] = ctx_app
            except Exception:
                pass
            steps: List[dict] = []
            for clause in clauses:
                resolved = _resolve_pronouns(clause, local_ctx)
                plan = _plan_single(resolved, use_llm=use_llm)
                # If bare "search X" follows an open_app, route to search_in_app
                prev_app = (steps[-1].get("app", "")
                            if steps and steps[-1].get("action") == "open_app"
                            else local_ctx.get("current_app", ""))
                if (plan.get("action") == "web_search"
                        and prev_app
                        and "search" in clause.lower()[:10]
                        and not re.search(r"\bin\b", clause.lower())):
                    plan = {
                        "action": "search_in_app_v2",
                        "query": plan.get("query", ""),
                        "app": prev_app,
                    }
                _update_context_from_plan(local_ctx, plan)
                steps.append(plan)
            logger.info("Multi-step plan (%d steps) generated for: %s", len(steps), text[:100])
            return {"steps": steps}

    # Single-action path
    plan = _plan_single(text, use_llm=use_llm)
    # If bare "search for X" standalone, route to search_in_app_v2 using
    # current_app from session memory (Issue 7)
    if plan.get("action") == "web_search" and "search" in text.lower()[:10]:
        try:
            import session_memory as _sm
            ctx_app = _sm.get("current_app")
            if ctx_app and not re.search(r"\bin\b", text.lower()):
                plan = {
                    "action": "search_in_app_v2",
                    "query": plan.get("query", ""),
                    "app": ctx_app,
                }
        except Exception:
            pass
    # Update session memory with the plan
    try:
        import session_memory as _sm
        _sm.update_from_plan(plan)
    except Exception:
        pass
    logger.info("Single-action plan: action=%s  text=%s", plan.get("action"), text[:100])
    return plan


def execute_plan(plan: dict) -> str:
    """Dispatch a plan to its registered handler. Returns a TTS-ready string.
    Supports structured error handling with status/skip/rollback."""
    if not isinstance(plan, dict):
        return "I received an invalid plan, sir."

    if "steps" in plan:
        results: List[str] = []
        for idx, step in enumerate(plan["steps"]):
            action = step.get("action", "unknown")
            logger.info("Executing step %d/%d: %s (step details: %s)",
                        idx + 1, len(plan["steps"]), action, step)
            step_start = time.time()
            try:
                result = _dispatch(step)
                elapsed = time.time() - step_start
                logger.info("Step %d/%d completed in %.2fs: %s",
                            idx + 1, len(plan["steps"]), elapsed, result[:80] if result else "None")
            except Exception as exc:
                elapsed = time.time() - step_start
                logger.error("Step %d/%d failed after %.2fs: %s — %s",
                             idx + 1, len(plan["steps"]), elapsed, action, exc)
                result = {"status": "failed", "step": idx + 1,
                          "reason": str(exc), "action": action}
                results.append(f"Step {idx + 1} ({action}) failed, sir.")
                continue
            if result:
                if isinstance(result, dict) and result.get("status") == "failed":
                    logger.warning("Step %d returned failure: %s", idx + 1, result.get("reason"))
                results.append(str(result).strip())
        if not results:
            return "All steps completed successfully, sir."
        if len(results) == 1:
            return results[0]
        successes = sum(1 for r in results if not r.startswith("Step ") or "failed" not in r)
        total = len(results)
        if successes == total:
            return ". ".join(results) + ". All tasks completed, sir."
        return ". ".join(results) + f". {successes} of {total} steps succeeded, sir."

    # Single action
    logger.info("Executing single action: %s", plan.get("action", "unknown"))
    step_start = time.time()
    result = _dispatch(plan)
    elapsed = time.time() - step_start
    logger.info("Single action completed in %.2fs", elapsed)
    return result if result else "Task completed, sir."
