"""Fast Command Router for Voice-First JARVIS.

Deterministic command processor that bypasses LLM for classification and
planning. Keyword pre-filter (O(k) where k = keyword count) followed by
regex pattern matching returns an action dict ready for the execution engine.
Does NOT execute commands — the caller routes the result through the engine.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Set, Callable, Any

from .windows_discovery import ApplicationResolver

logger = __import__("logging").getLogger("jarvis.fast_command_router")

FAST_COMMAND_KEYWORDS: Set[str] = {
    "open chrome", "open edge", "open settings", "open calculator",
    "play music", "pause music", "next track", "previous track",
    "volume up", "volume down", "mute", "unmute",
    "take screenshot", "lock pc", "shutdown", "restart",
    "show desktop", "open terminal", "open steam", "open file explorer",
    "what time is it", "what is the time", "current time",
    "what is the date", "what day is it", "today",
    "search", "google", "youtube", "weather",
    "cpu", "ram", "disk", "battery", "gpu", "memory",
    "open notepad", "open paint", "open word", "open vs code",
    "play", "pause", "stop", "skip", "next", "previous",
}

FAST_COMMAND_PATTERNS = [
    (re.compile(r"open\s+(?P<app>chrome|edge|settings|calculator|notepad|paint|word|steam|terminal|file\s*explorer)", re.I), "open_app"),
    (re.compile(r"volume\s+(?P<op>up|down|mute|unmute)", re.I), "volume_control"),
    (re.compile(r"(take\s+)?screenshot", re.I), "screenshot"),
    (re.compile(r"lock\s+pc|lock\s+computer", re.I), "pc_control"),
    (re.compile(r"show\s+desktop", re.I), "show_desktop"),
    (re.compile(r"shutdown|restart|power\s+off", re.I), "pc_control"),
    (re.compile(r"play\s+music|pause\s+music|next\s+track|previous\s+track|music\s+(play|pause|next|previous)", re.I), "music"),
    (re.compile(r"play\s+(?P<query>.+?)\s+in\s+(?P<app>\w+)", re.I), "play_in_app"),
    (re.compile(r"play\s+(?P<query>.+)", re.I), "music"),
    (re.compile(r"remind\s+me\s+(?P<text>.+)", re.I), "reminder"),
    (re.compile(r"set\s+a\s+reminder\s+in\s+(?P<minutes>\d+)\s+minutes?\s+to?\s+(?P<text>.+)", re.I), "reminder"),
    (re.compile(r"(what|tell\s+me)\s+(?:the\s+)?time|what\s+time\s+is\s+it", re.I), "time"),
    (re.compile(r"(what|tell\s+me)\s+(is\s+)?the\s+date|what\s+day\s+is\s+it", re.I), "date"),
    (re.compile(r"cpu|processor", re.I), "system_stats"),
    (re.compile(r"ram|memory", re.I), "system_stats"),
    (re.compile(r"battery|charge", re.I), "system_stats"),
    (re.compile(r"what.*weather", re.I), "weather"),
    (re.compile(r"search\s+(?:the\s+web\s+for\s+)?(?P<query>.+)", re.I), "web_search"),
]


class FastCommandRouter:
    """Deterministic fast command router for Voice-First JARVIS."""

    def __init__(self, app_resolver: Optional[ApplicationResolver] = None):
        self._app_resolver = app_resolver
        self._app_resolver_created = app_resolver is not None
        self._command_handlers: Dict[str, Callable] = {}
        self._register_handlers()

    @property
    def app_resolver(self) -> ApplicationResolver:
        if not self._app_resolver_created:
            self._app_resolver = ApplicationResolver()
            self._app_resolver_created = True
        return self._app_resolver

    def _register_handlers(self):
        self._command_handlers = {
            "open_app": self._handle_open_app,
            "volume_control": self._handle_volume_control,
            "screenshot": self._handle_screenshot,
            "pc_control": self._handle_pc_control,
            "show_desktop": self._handle_show_desktop,
            "music": self._handle_music,
            "reminder": self._handle_reminder,
            "time": self._handle_time,
            "date": self._handle_date,
            "system_stats": self._handle_system_stats,
        }

    def _is_fast_command(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in FAST_COMMAND_KEYWORDS)

    def route(self, text: str) -> Optional[Dict[str, Any]]:
        if not text or not text.strip():
            return None
        if not self._is_fast_command(text):
            return None
        lower = text.lower()
        for pattern, action in FAST_COMMAND_PATTERNS:
            m = pattern.search(lower)
            if m:
                handler = self._command_handlers.get(action)
                if handler:
                    return handler(m.groupdict() if m.lastindex else {})
                return {"action": action, "params": m.groupdict() if m.lastindex else {}}
        return None

    def _handle_open_app(self, params: dict) -> dict:
        app_name = params.get("app", "")
        if app_name:
            result = self.app_resolver.find_app(app_name)
            if result:
                return {"action": "open_app", "app": result.name, "path": result.path, "response": f"Opening {result.name}, sir."}
        return {"action": "open_app", "response": f"Opening {app_name}, sir."}

    def _handle_volume_control(self, params: dict) -> dict:
        op = params.get("op", "up")
        return {"action": "volume_control", "op": op, "response": f"Volume {op}, sir."}

    def _handle_screenshot(self, params: dict) -> dict:
        return {"action": "screenshot", "response": "Taking screenshot, sir."}

    def _handle_pc_control(self, params: dict) -> dict:
        phrase = params.get("phrase", "")
        return {"action": "pc_control", "phrase": phrase, "response": f"Executing: {phrase}, sir."}

    def _handle_show_desktop(self, params: dict) -> dict:
        return {"action": "show_desktop", "response": "Showing desktop, sir."}

    def _handle_music(self, params: dict) -> dict:
        op = params.get("op", "play")
        return {"action": "music", "op": op, "response": f"Music {op}, sir."}

    def _handle_reminder(self, params: dict) -> dict:
        return {"action": "reminder", "response": "Reminder set, sir."}

    def _handle_time(self, params: dict) -> dict:
        from datetime import datetime
        return {"action": "time", "response": f"The time is {datetime.now().strftime('%I:%M %p')}, sir."}

    def _handle_date(self, params: dict) -> dict:
        from datetime import datetime
        return {"action": "date", "response": f"Today is {datetime.now().strftime('%A, %B %d, %Y')}, sir."}

    def _handle_system_stats(self, params: dict) -> dict:
        return {"action": "system_stats", "response": "Fetching system stats."}

    def process(self, text: str) -> Optional[Dict[str, Any]]:
        return self.route(text)


_fast_router: Optional[FastCommandRouter] = None


def get_fast_router() -> FastCommandRouter:
    global _fast_router
    if _fast_router is None:
        _fast_router = FastCommandRouter()
    return _fast_router


def route_fast_command(text: str) -> Optional[Dict[str, Any]]:
    return get_fast_router().process(text)