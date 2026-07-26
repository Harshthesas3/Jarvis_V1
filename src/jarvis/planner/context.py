"""Context management for multi-step plans: pronoun resolution and execution context."""

from __future__ import annotations

import os
import re
from typing import Dict, Optional

from .aliases import resolve_alias_path

# Initial context for a plan action call
_INITIAL_CONTEXT: Dict[str, str] = {
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

# Multi-step intent detection regex (copied from the original planner.py)
_MULTI_STEP_DETECT_RE = re.compile(
    r"[,;]"
    r"|\b(?:and\s+then|then\s+after\s+that|after\s+that|next|also|finally|followed\s+by|plus)\b"
    r"|\b(?:and|then)\b\s*"
    r"(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make"
    r"|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause"
    r"|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze"
    r"|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell"
    r"|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press"
    r"|scroll|click|double|right|run|execute|generate|wait))"
    # "after X, do Y" patterns
    r"|\bafter\s+.+?(?:\s*)?(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make"
    r"|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause"
    r"|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze"
    r"|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell"
    r"|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press"
    r"|scroll|click|double|right|run|execute|generate|wait)",
    re.IGNORECASE,
)


def has_multi_step_intent(text: str) -> bool:
    """Return True if the text looks like it contains multiple steps."""
    return bool(_MULTI_STEP_DETECT_RE.search(text))


def _resolve_pronouns(text: str, ctx: Dict[str, str]) -> str:
    """Resolve pronouns (it, there, this, that) using the execution context."""
    result = text
    file_ref = ctx.get("current_file") or ctx.get("last_file", "")
    folder_ref = ctx.get("current_folder") or ctx.get("last_folder", "")
    # Build combined path for "it" when both file and folder are known
    combined_ref: str = file_ref or folder_ref
    if folder_ref and file_ref and "/" not in file_ref and "\\" not in file_ref:
        combined_ref = folder_ref.rstrip("/\\") + "/" + file_ref
    # Resolve "it"
    if combined_ref:
        result = re.sub(r"(?<![a-zA-Z])it(?![a-zA-Z])", combined_ref, result)
    # Resolve "there" to the current folder
    if folder_ref:
        result = re.sub(r"(?<![a-zA-Z])there(?![a-zA-Z])", folder_ref, result)
    # Resolve "this" to clipboard or screenshot content
    this_val = ctx.get("last_clipboard") or ctx.get("last_screenshot") or ""
    if this_val:
        result = re.sub(r"(?<![a-zA-Z])this(?![a-zA-Z])", this_val, result)
    # Resolve "that" to last search result
    if ctx.get("last_search_result"):
        result = re.sub(r"(?<![a-zA-Z])that(?![a-zA-Z])", ctx["last_search_result"], result)
    # Additional pronoun support
    if combined_ref:
        result = re.sub(r"(?<![a-zA-Z])them(?![a-zA-Z])", combined_ref, result)
    return result


def _update_context_from_plan(ctx: Dict[str, str], plan: dict) -> None:
    """Update the execution context based on a single action plan."""
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
            ctx["last_file"] = ppath or pname
            ctx["current_file"] = ppath or pname
    if action == "clipboard" and op == "write":
        ctx["last_clipboard"] = plan.get("text", "")
    if action == "open_app":
        app = plan.get("app", "")
        ctx["last_app"] = app
        ctx["current_app"] = app
    if action in ("switch_window",):
        target = plan.get("target", "")
        if target:
            ctx["current_app"] = target
            ctx["current_window"] = target
    if action == "web_search":
        ctx["last_search_result"] = plan.get("query", "")
    if action in ("focus_window", "wait_for_window"):
        title = plan.get("title", "") or plan.get("target", "")
        if title:
            ctx["current_window"] = title
    if action in ("search_in_app", "search_in_app_v2"):
        ctx["current_app"] = plan.get("app", "")
        ctx["current_window"] = plan.get("app", "")


def needs_clarification(text: str) -> Optional[dict]:
    """Check if the user's request is incomplete and return a clarification prompt if so."""
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