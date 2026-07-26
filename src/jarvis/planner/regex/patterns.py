"""Fast-path regex triggers and builders for the planner.

This module contains the compiled regex patterns and their corresponding
builder lambdas that map matched groups to action dicts.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Callable, Dict, List, Tuple, Pattern, Any

from ..config import get_planner_model
from ..metrics import get_metrics

logger = logging.getLogger("jarvis.planner.regex")

# ---------------------------------------------------------------------------
# Helper functions used by many builders
# ---------------------------------------------------------------------------

_TRAILING_PUNCTUATION_RE = re.compile(r"[.,!?;:]+$")


def _strip_query_punctuation(query: str) -> str:
    return _TRAILING_PUNCTUATION_RE.sub("", query).strip()


def _strip_file_name(name: str) -> str:
    name = name.strip()
    if "." in name:
        base, ext = name.rsplit(".", 1)
        base = _TRAILING_PUNCTUATION_RE.sub("", base).strip()
        ext = _TRAILING_PUNCTUATION_RE.sub("", ext).strip()
        if ext:
            return f"{base}.{ext}"
    return _TRAILING_PUNCTUATION_RE.sub("", name).strip()


def _resolve_path(text: str) -> str:
    from ..aliases import resolve_alias_path
    return resolve_alias_path(text)


# ---------------------------------------------------------------------------
# Builder functions (lambda equivalents)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Trigger registry
# ---------------------------------------------------------------------------

_TRIGGERS: List[Tuple[Pattern[str], Callable[[re.Match, str], dict | None]]] = []


def _add_trigger(pattern_str: str, builder: Callable[[re.Match, str], dict | None], flags: int = re.IGNORECASE) -> None:
    _TRIGGERS.append((re.compile(pattern_str, flags), builder))


# Close app
_add_trigger(
    r"^(?:please\s+)?(?:close|quit|exit)\s+(?P<app>.+?)\s*$",
    lambda m, src: {"action": "close_app", "app": m.group("app").strip()},
)

# Browser open (must come before switch_window)
_add_trigger(
    r"^(?:please\s+)?(?:open\s+browser\s+(?:to|at)\s+|go\s+to\s+)"
    r"(?P<url>https?://\S+|www\.\S+|\S+\.\w{2,}(?:/\S*)?)\s*$",
    lambda m, src: {"action": "browser_open", "url": m.group("url").strip()},
)

# Switch window
_add_trigger(
    r"^(?:please\s+)?(?:switch|go)\s+to\s+(?P<target>.+?)\s*$",
    lambda m, src: {"action": "switch_window", "target": m.group("target").strip()},
)

# Open folder
_add_trigger(
    r"^(?:please\s+)?open\s+folder\s+(?P<path>.+?)\s*$",
    lambda m, src: {"action": "open_folder", "path": m.group("path").strip()},
)

# Rename folder
_add_trigger(
    r"^(?:please\s+)?rename\s+(?:the\s+)?folder\s+"
    r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<new_name>[\w.\- ]+)$",
    lambda m, src: {
        "action": "folder_operation",
        "op": "rename_folder",
        "path": m.group("path").strip(),
        "new_name": m.group("new_name").strip(),
    },
)

# Append to file
_add_trigger(
    r"^(?:please\s+)?(?:append|add)\s+(?P<content>.+?)\s+to\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
    lambda m, src: {
        "action": "file_operation",
        "op": "append_file",
        "path": m.group("path").strip(),
        "content": m.group("content").strip(),
    },
)

# Search in app (negative lookahead for files)
_add_trigger(
    r"^(?:please\s+)?search\s+(?:for\s+)?(?P<query>.+?)\s+in\s+(?!files?\s*$)(?P<app>.+?)$",
    lambda m, src: {
        "action": "search_in_app_v2",
        "query": _strip_query_punctuation(m.group("query")),
        "app": m.group("app").strip(),
    },
)

# Click
_add_trigger(
    r"^(?:please\s+)?click\s+"
    r"(?:(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?)?"
    r"(?:\s*(?P<button>left|right|middle))?\s*$",
    lambda m, src: {
        "action": "click",
        "x": int(m.group("x")) if m.group("x") else None,
        "y": int(m.group("y")) if m.group("y") else None,
        "button": (m.group("button") or "left").lower(),
    },
)

# Double-click
_add_trigger(
    r"^(?:please\s+)?double\s*click\s+"
    r"(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?\s*$",
    lambda m, src: {
        "action": "double_click",
        "x": int(m.group("x")) if m.group("x") else None,
        "y": int(m.group("y")) if m.group("y") else None,
    },
)

# Right-click
_add_trigger(
    r"^(?:please\s+)?right\s*click\s+"
    r"(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?\s*$",
    lambda m, src: {
        "action": "right_click",
        "x": int(m.group("x")) if m.group("x") else None,
        "y": int(m.group("y")) if m.group("y") else None,
    },
)

# Type text
_add_trigger(
    r"^(?:please\s+)?type\s+(?P<text>.+?)\s*$",
    lambda m, src: {"action": "type_text", "text": m.group("text").strip()},
)

# Press key
_add_trigger(
    r"^(?:please\s+)?press\s+(?P<key>.+?)\s*$",
    lambda m, src: {"action": "press_key", "key": m.group("key").strip()},
)

# Scroll
_add_trigger(
    r"^(?:please\s+)?scroll\s+"
    r"(?P<dir>up|down|left|right)?\s*"
    r"(?P<amount>\d+)?\s*$",
    lambda m, src: {
        "action": "scroll",
        "direction": (m.group("dir") or "down").lower(),
        "amount": int(m.group("amount")) if m.group("amount") else 3,
    },
)

# Browser search
_add_trigger(
    r"^(?:please\s+)?search\s+in\s+(?:the\s+)?browser\s+for\s+(?P<query>.+?)\s*$",
    lambda m, src: {"action": "browser_search", "query": _strip_query_punctuation(m.group("query"))},
)

# Browser click
_add_trigger(
    r"^(?:please\s+)?click\s+on\s+(?P<element>.+?)\s+in\s+(?:the\s+)?browser\s*$",
    lambda m, src: {"action": "browser_click", "element": m.group("element").strip()},
)

# Diagnostics
_add_trigger(
    r"^(?:run\s+)?diagnostics\s*$",
    lambda m, src: {"action": "diagnostics"},
)

# Run program (must come after run_command)
_add_trigger(
    r"^(?:please\s+)?run\s+(?!command\s)(?P<program>.+?)\s*$",
    lambda m, src: {"action": "run_program", "program": m.group("program").strip()},
)

# Run terminal command
_add_trigger(
    r"^(?:please\s+)?(?:run\s+command|execute)\s+(?P<command>.+?)\s*$",
    lambda m, src: {
        "action": "run_terminal_command",
        "command": m.group("command").strip(),
    },
)

# Generate code
_add_trigger(
    r"^(?:please\s+)?(?:generate|write)\s+code\s+(?:for|to)\s+(?P<description>.+?)\s*$",
    lambda m, src: {
        "action": "generate_code",
        "description": m.group("description").strip(),
    },
)

# Wait
_add_trigger(
    r"^(?:please\s+)?wait\s+(?:for\s+)?(?P<seconds>\d+)\s*(?:seconds?|secs?)?\s*$",
    lambda m, src: {"action": "wait", "seconds": int(m.group("seconds"))},
)

# PC control (many phrases)
_add_trigger(
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
    r"|open\s+(?:the\s+)?device\s+manager"
    r"|open\s+services"
    r"|open\s+downloads?(?:\s+folder)?"
    r"|open\s+documents?(?:\s+folder)?"
    r"|open\s+(?:my\s+)?desktop"
    r"|open\s+(?:the\s+)?recycle\s+bin"
    r"|open\s+(?:the\s+)?recycle"
    r")\s*$",
    lambda m, src: {
        "action": "pc_control",
        "phrase": m.group("phrase").strip().lower(),
    },
)

# Standalone noun phrases for PC
_add_trigger(
    r"^(?P<phrase>downloads?|downloads?\s+folder|"
    r"documents?|documents?\s+folder|"
    r"desktop|recycle\s+bin|recycle|"
    r"task\s+manager|control\s+panel|"
    r"device\s+manager|services|registry(?:\s+editor)?)$",
    lambda m, src: {
        "action": "pc_control",
        "phrase": m.group("phrase").strip().lower(),
    },
)

# File open (must come before generic open_app)
_add_trigger(
    r"^(?:please\s+)?(?:open|launch|show)\s+(?:the\s+)?(?:file\s+)?(?P<path>[\w.\- /\\:]+?\.[a-zA-Z0-9]{1,5})$",
    lambda m, src: {
        "action": "file_operation",
        "op": "open_file",
        "path": m.group("path").strip(),
    },
)

# Clipboard read
_add_trigger(
    r"^read\s+my\s+clipboard$|^what(?:'s|\s+is)\s+on\s+my\s+clipboard$",
    lambda m, src: {"action": "clipboard", "op": "read"},
)
_add_trigger(
    r"^read\s+(?:the\s+)?clipboard$",
    lambda m, src: {"action": "clipboard", "op": "read"},
)
_add_trigger(
    r"^what(?:'s|\s+is)\s+on\s+(?:the\s+)?clipboard$",
    lambda m, src: {"action": "clipboard", "op": "read"},
)
_add_trigger(
    r"^(?:summarize|explain)\s+(?:my\s+)?clipboard$",
    lambda m, src: {"action": "clipboard", "op": "summarize"},
)
_add_trigger(
    r"^(?:copy|put|write)\s+(?P<text>.+?)\s+(?:to|on)\s+(?:my\s+)?clipboard$",
    lambda m, src: {
        "action": "clipboard",
        "op": "write",
        "text": m.group("text").strip(),
    },
)

# Time / date (must come before web_search "what is")
_add_trigger(
    r"^what(?:'s|\s+is)\s+the\s+time(?:\s+now)?$",
    lambda m, src: {"action": "time"},
)
_add_trigger(
    r"^what\s+time\s+is\s+it(?:\s+now)?$",
    lambda m, src: {"action": "time"},
)
_add_trigger(
    r"^what(?:'s|\s+is)\s+(?:the\s+)?(?:today(?:'s)?\s+)?date$",
    lambda m, src: {"action": "date"},
)
_add_trigger(
    r"^what\s+(?:day|date)\s+is\s+(?:it|today)$",
    lambda m, src: {"action": "date"},
)
_add_trigger(
    r"^(?:battery|cpu|ram|memory(?:\s+usage)?|system\s+stats?)$",
    lambda m, src: {"action": "system_stats", "metric": m.group(0).lower()},
)

# File search
_add_trigger(
    r"^(?:please\s+)?search\s+(?:for\s+)?files?\s+"
    r"(?:containing|matching|named)\s+(?P<query>.+?)$",
    lambda m, src: {
        "action": "file_operation",
        "op": "search_files",
        "query": m.group("query").strip(),
    },
)
_add_trigger(
    r"^(?:please\s+)?search\s+(?:for\s+)?(?P<query>.+?)\s+"
    r"(?:in\s+files?|across\s+files?)$",
    lambda m, src: {
        "action": "file_operation",
        "op": "search_files",
        "query": m.group("query").strip(),
    },
)

# Open app (single-app launch)
_add_trigger(
    r"^open\s+(?P<app>[a-zA-Z][\w\s.\-]*?)\s*$",
    lambda m, src: (
        None
        if re.search(r"\b(?:and|then|after\s+that|also|plus)\b", m.group("app"), re.IGNORECASE)
        or (
            len(m.group("app").split()) >= 3
            and re.search(r"\b(?:my|a|an|this|that|most|all|these|those|"
                          r"some|any|every|each|important|main|current|recent|"
                          r"previous|next|first|last|second)\b",
                          m.group("app"), re.IGNORECASE)
        )
        else {"action": "open_app", "app": m.group("app").strip()}
    ),
)

# Launch/start/run app
_add_trigger(
    r"^(?:launch|start|run)\s+(?P<app>[a-zA-Z][\w\s.\-]*?)\s*$",
    lambda m, src: (
        None
        if re.search(r"\b(?:and|then|after\s+that|also|plus)\b", m.group("app"), re.IGNORECASE)
        else {"action": "open_app", "app": m.group("app").strip()}
    ),
)

# Reminder time/task
_add_trigger(
    r"^(?:remind\s+me\s+)?(?:at|on)?\s*"
    r"(?P<time>tomorrow\s+\d{1,2}(::\d{2})?\s*(?:am|pm)?|"
    r"today\s+\d{1,2}(::\d{2})?\s*(?:am|pm)?|"
    r"\d{1,2}(::\d{2})?\s*(?:am|pm)|"
    r"tomorrow|tonight|tonight\s+at\s+\d{1,2}(::\d{2})?\s*(?:am|pm)?)\s+"
    r"to\s+(?P<task>.+)$",
    lambda m, src: {
        "action": "reminder",
        "time": m.group("time").strip(),
        "task": m.group("task").strip(),
    },
)
# WhatsApp
_add_trigger(
    r"^(?:message|whatsapp|send\s+whatsapp(?:\s+message)?\s+to)\s+"
    r"(?P<contact>[a-zA-Z][\w\s]{0,40}?)\s+"
    r"(?:that\s+)?(?P<message>.+)$",
    lambda m, src: {
        "action": "whatsapp",
        "contact": m.group("contact").strip(),
        "message": m.group("message").strip(),
    },
)
_add_trigger(
    r"^show\s+reminders?$|^list\s+reminders?$",
    lambda m, src: {"action": "reminder", "op": "list"},
)
_add_trigger(
    r"^clear\s+reminders?$",
    lambda m, src: {"action": "reminder", "op": "clear"},
)
_add_trigger(
    r"^(?:delete|remove)\s+reminder\s+(?P<idx>\d+)$",
    lambda m, src: {
        "action": "reminder",
        "op": "remove",
        "index": int(m.group("idx")),
    },
)
# WhatsApp
_add_trigger(
    r"^(?:message|whatsapp|send\s+whatsapp(?:\s+message)?\s+to)\s+"
    r"(?P<contact>[a-zA-Z][\w\s]{0,40}?)\s+"
    r"(?:that\s+)?(?P<message>.+)$",
    lambda m, src: {
        "action": "whatsapp",
        "contact": m.group("contact").strip(),
        "message": m.group("message").strip(),
    },
)

# WhatsApp
_add_trigger(
    r"^(?:message|whatsapp|send\s+whatsapp(?:\s+message)?\s+to)\s+"
    r"(?P<contact>[a-zA-Z][\w\s]{0,40}?)\s+"
    r"(?:that\s+)?(?P<message>.+)$",
    lambda m, src: {
        "action": "whatsapp",
        "contact": m.group("contact").strip(),
        "message": m.group("message").strip(),
    },
)
# tell <name> <message>
_add_trigger(
    r"\btell\s+(?P<contact>"
    r"mom|dad|brother|sister|friend|bhajan|"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"
    r")\s+"
    r"(?:that\s+)?(?P<message>.+?)$",
    lambda m, src: {
        "action": "whatsapp",
        "contact": m.group("contact").strip(),
        "message": m.group("message").strip(),
    },
)

# Email
_add_trigger(
    r"^(?:email|draft\s+(?:an\s+)?email(?:\s+to)?)\s+"
    r"(?P<recipient>[a-zA-Z][\w\s]{0,40}?)\s+"
    r"(?:about|with|re:)?\s*(?P<subject>.+?)\s+"
    r"saying\s+(?P<body>.+)$",
    lambda m, src: {
        "action": "email",
        "recipient": m.group("recipient").strip(),
        "subject": m.group("subject").strip(),
        "body": m.group("body").strip(),
    },
)
_add_trigger(
    r"^(?:email|draft\s+(?:an\s+)?email(?:\s+to)?)\s+"
    r"(?P<recipient>[a-zA-Z][\w\s]{0,40}?)\s+"
    r"(?:about|with|re:)?\s*(?P<subject>.+)$",
    lambda m, src: {
        "action": "email",
        "recipient": m.group("recipient").strip(),
        "subject": m.group("subject").strip(),
        "body": "",
    },
)

# Screen awareness
_add_trigger(
    r"^what(?:'s|\s+is)\s+on\s+my\s+screen$|^read\s+my\s+screen$|"
    r"^describe\s+(?:my\s+)?screen$|^describe\s+this\s+page$",
    lambda m, src: {"action": "screen_awareness", "op": "describe"},
)
_add_trigger(
    r"^(?:analyze|explain)\s+this\s+error$|"
    r"^what\s+error(?:\s+is\s+(?:this|shown))?$|"
    r"^help\s+me\s+(?:fix|solve)\s+this(?:\s+error)?$",
    lambda m, src: {"action": "screen_awareness", "op": "error"},
)
_add_trigger(
    r"^(?:explain|review)\s+this\s+code$",
    lambda m, src: {"action": "screen_awareness", "op": "code_review"},
)
_add_trigger(
    r"^(?:read|summarize)\s+this\s+(?:page|document)$",
    lambda m, src: {"action": "screen_awareness", "op": "summarize_document"},
)

# Web search (what is / who is)
_add_trigger(
    r"^(?:what\s+is|who\s+is|whats|what's)\s+(?P<query>.+?)\??$",
    lambda m, src: {
        "action": "web_search",
        "query": _strip_query_punctuation(m.group("query")),
    },
)

# Memory
_add_trigger(
    r"^remember\s+that\s+(?P<fact>.+)$",
    lambda m, src: {"action": "memory_store", "fact": m.group("fact").strip()},
)
_add_trigger(
    r"^remember\s+(?P<fact>.+)$",
    lambda m, src: {"action": "memory_store", "fact": m.group("fact").strip()},
)
_add_trigger(
    r"^what\s+do\s+you\s+remember$|^recall(?:\s+memory)?$",
    lambda m, src: {"action": "memory_recall"},
)
_add_trigger(
    r"^forget\s+everything$|^clear\s+(?:your\s+)?memory$",
    lambda m, src: {"action": "memory_clear"},
)

# Screenshot
_add_trigger(
    r"^(?:screenshot|take\s+a\s+screenshot|capture\s+screen)$",
    lambda m, src: {"action": "screenshot"},
)

# Volume
_add_trigger(
    r"^volume\s+(?P<dir>up|down|mute|unmute)$",
    lambda m, src: {
        "action": "volume_control",
        "op": m.group("dir").lower(),
    },
)
_add_trigger(
    r"^set\s+volume\s+to\s+(?P<level>\d+)\s*(?:percent)?%?$",
    lambda m, src: {
        "action": "volume_control",
        "op": "set",
        "level": int(m.group("level")),
    },
)

# Music
_add_trigger(
    r"^(?P<op>play|pause|stop|next|previous|skip)\s+(?:music|song|track)$",
    lambda m, src: {"action": "music", "op": m.group("op").lower()},
)

# System control (lock/shutdown/restart)
_add_trigger(
    r"^(?P<op>lock(?:\s+computer)?|shutdown(?:\s+computer)?|"
    r"restart(?:\s+computer)?)$",
    lambda m, src: {"action": "system_control", "op": m.group(0).lower().split()[0]},
)

# Clipboard clear
_add_trigger(
    r"^(?:clear|empty|wipe)\s+(?:my\s+)?clipboard$",
    lambda m, src: {"action": "clipboard", "op": "clear"},
)

# Detect overlapping patterns at module load
def _detect_regex_conflicts(triggers: List[Tuple[Pattern[str], Callable[[re.Match, str], dict | None]]]) -> None:
    for i, (p1, _) in enumerate(triggers):
        for j, (p2, _) in enumerate(triggers):
            if i >= j:
                continue
            # Check if p1's match region could overlap p2's on synthetic inputs
            s1, s2 = p1.pattern[:60], p2.pattern[:60]
            try:
                test = "open calculator and open notepad"
                m1 = p1.match(test)
                m2 = p2.match(test)
                if m1 and m2 and m1.group(0) != m2.group(0):
                    logger.debug("Potential overlap #%d <-> #%d: %s | %s", i, j, s1, s2)
            except Exception:
                pass


def build_triggers() -> List[Tuple[Pattern[str], Callable[[re.Match, str], dict | None]]]:
    """Return the list of (pattern, builder) tuples for the fast-path."""
    return list(_TRIGGERS)


def _try_fast_path(user_text: str) -> Optional[dict]:
    """Try the fast-path regex matchers. Returns a plan dict or None."""
    src = user_text.strip()
    triggers = build_triggers()
    for pattern, builder in triggers:
        m = pattern.match(src)
        if m:
            result = builder(m, src)
            if result is not None:
                get_metrics().record(fast_path_hits=1)
                return result
    get_metrics().record(fast_path_misses=1)
    return None