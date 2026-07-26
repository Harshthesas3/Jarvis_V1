"""Capability resolution — maps intent domains to capability handlers."""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from ..llm import extract_json, llm_chat_with_retry
from ..config import get_planner_model

logger = logging.getLogger("jarvis.planner.capabilities")

# Intent -> capability default map
_INTENT_TO_CAPABILITY: dict[str, str] = {
    "conversation": "general_chat",
    "scheduling": "scheduler",
    "project_analysis": "file_search",
    "memory": "memory_store",
    "web_search": "web_browser",
    "communication": "communication",
    "app_control": "app_launcher",
    "system_control": "system_commands",
    "media_control": "media_player",
    "time_date": "clock",
    "clipboard": "clipboard",
    "screenshot": "screenshot",
    "screen_awareness": "screen_awareness",
    "diagnostics": "diagnostics",
    "code_generation": "code_generator",
    "terminal_command": "terminal",
    "desktop_automation": "desktop_automation",
    "browser": "browser",
    "file_management": "file_manager",
}

_CAPABILITY_HANDLERS: Dict[str, Callable[[dict, str], Optional[dict]]] = {}


def register_capability(name: str) -> Callable:
    """Decorator to register a capability handler function."""
    def decorator(fn: Callable) -> Callable:
        _CAPABILITY_HANDLERS[name] = fn
        return fn
    return decorator


def resolve_capability(intent: dict) -> str:
    """Map classified intent to the capability that should handle it."""
    req = intent.get("required_capabilities", [])
    for cap in req:
        if cap in _CAPABILITY_HANDLERS:
            return cap
    return _INTENT_TO_CAPABILITY.get(intent.get("intent", ""), "general_chat")


def invoke_capability(capability: str, intent: dict, user_text: str) -> Optional[dict]:
    """Dispatch to a registered capability handler."""
    handler = _CAPABILITY_HANDLERS.get(capability)
    if handler is None:
        logger.warning("No handler for capability: %s", capability)
        return None
    return handler(intent, user_text)


def get_registered_capabilities() -> Dict[str, Callable]:
    return dict(_CAPABILITY_HANDLERS)


def _cap_llm(prompt: str, text: str) -> Optional[dict]:
    """Call LLM with a capability-specific system prompt."""
    resp = llm_chat_with_retry(
        model=get_planner_model(),
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
        num_predict=400,
    )
    if resp is None:
        return None
    try:
        raw = resp["message"]["content"]
        return extract_json(raw)
    except Exception as exc:
        logger.warning("Capability LLM call parsing failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Capability handlers
# ---------------------------------------------------------------------------

@register_capability("general_chat")
def _cap_general_chat(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a helpful AI assistant.\nOutput a JSON action plan:\n"
        '  {"action": "ai_chat", "text": "<response>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("scheduler")
def _cap_scheduler(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a scheduling assistant.\nOutput a JSON action plan:\n"
        '  {"action": "ai_chat", "text": "<helpful scheduling response>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("file_search")
def _cap_file_search(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a file-search assistant.\nOutput a JSON action plan:\n"
        '  {"action": "file_operation", "op": "search_files", "query": "<query>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("web_browser")
def _cap_web_browser(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a web search assistant.\nOutput a JSON action plan:\n"
        '  {"action": "web_search", "query": "<query>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("communication")
def _cap_communication(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a messaging assistant. Determine WhatsApp or email.\n"
        'WhatsApp: {"action": "whatsapp", "contact": "<name>", "message": "<message>"}\n'
        'Email: {"action": "email", "recipient": "<name>", "subject": "<subject>", "body": "<body>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@register_capability("app_launcher")
def _cap_app_launcher(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, an app control assistant. Determine open or close.\n"
        'Open: {"action": "open_app", "app": "<app name>"}\n'
        'Close: {"action": "close_app", "app": "<app name>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("system_commands")
def _cap_system_commands(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a system control assistant.\n"
        '{"action": "system_control", "op": "<lock/shutdown/restart/sleep>"}\n'
        '{"action": "volume_control", "op": "<up/down/mute/unmute/set>", "level": <0-100>}\n'
        "Output ONLY the JSON.",
        text,
    )


@register_capability("media_player")
def _cap_media_player(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a media control assistant.\n"
        '{"action": "music", "op": "<play/pause/stop/next/previous>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("code_generator")
def _cap_code_generator(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a code generation assistant.\n"
        '{"action": "generate_code", "description": "<what>", "language": "<lang>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("file_manager")
def _cap_file_manager(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a file management assistant.\n"
        '{"action": "file_operation", "op": "<op>", "name/path/query": "..."}\n'
        '{"action": "folder_operation", "op": "<op>", "name/path": "..."}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("browser")
def _cap_browser(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a browser control assistant.\n"
        '{"action": "browser_open", "url": "<url>"}\n'
        '{"action": "browser_search", "query": "<query>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("terminal")
def _cap_terminal(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a terminal assistant.\n"
        '{"action": "run_terminal_command", "command": "<cmd>"}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("desktop_automation")
def _cap_desktop_automation(intent: dict, text: str) -> Optional[dict]:
    return _cap_llm(
        "You are JARVIS, a desktop automation assistant.\n"
        '{"action": "type_text", "text": "..."}\n'
        '{"action": "press_key", "key": "..."}\n'
        '{"action": "click", "x": <num>, "y": <num>}\nOutput ONLY the JSON.',
        text,
    )


@register_capability("clock")
def _cap_clock(intent: dict, text: str) -> Optional[dict]:
    t = text.lower()
    return {"action": "date"} if "date" in t else {"action": "time"}


@register_capability("screenshot")
def _cap_screenshot(intent: dict, text: str) -> Optional[dict]:
    return {"action": "screenshot"}


@register_capability("diagnostics")
def _cap_diagnostics(intent: dict, text: str) -> Optional[dict]:
    return {"action": "diagnostics"}


@register_capability("clipboard")
def _cap_clipboard(intent: dict, text: str) -> Optional[dict]:
    t = text.lower()
    if any(w in t for w in ("clear", "empty", "wipe")):
        return {"action": "clipboard", "op": "clear"}
    if any(w in t for w in ("write", "copy", "put")):
        return {"action": "clipboard", "op": "write", "text": text}
    return {"action": "clipboard", "op": "read"}


@register_capability("screen_awareness")
def _cap_screen_awareness(intent: dict, text: str) -> Optional[dict]:
    t = text.lower()
    if "error" in t:
        return {"action": "screen_awareness", "op": "error"}
    if "code" in t or "review" in t:
        return {"action": "screen_awareness", "op": "code_review"}
    if "summarize" in t or "document" in t or "page" in t:
        return {"action": "screen_awareness", "op": "summarize_document"}
    return {"action": "screen_awareness", "op": "describe"}


@register_capability("memory_store")
def _cap_memory_store(intent: dict, text: str) -> Optional[dict]:
    t = text.lower()
    if "recall" in t or "remember" in t or "what do you" in t:
        return {"action": "memory_recall"}
    if "forget" in t or "clear" in t:
        return {"action": "memory_clear"}
    return {"action": "memory_store", "fact": text}