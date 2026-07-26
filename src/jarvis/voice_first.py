"""Voice-First JARVIS Integration Module.

Voice is the DEFAULT interaction model — no Voice Mode button, no toggles.
Two states: PASSIVE (wake word detection) → ACTIVE (continuous conversation).
Dismissal phrases end the ACTIVE state. VoiceFirstBackend.classify() returns
action dicts for fast-commands only; execution is handled by the caller via
the execution engine or legacy handlers.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("jarvis.voice_first")

from jarvis.fast_command_router import FAST_COMMAND_KEYWORDS, FAST_COMMAND_PATTERNS

WAKE_WORDS = ["i am back", "im back", "hey jarvis", "jarvis", "ok jarvis"]
DISMISS_PHRASES = [
    "bye", "goodbye", "thank you", "thanks", "sleep",
    "stop listening", "go to sleep", "exit",
]


_REMINDER_SPEECH_CORRECTIONS = {
    "remainder": "reminder",
    "remender": "reminder",
    "remidner": "reminder",
}


def correct_speech(text: str) -> str:
    for wrong, right in _REMINDER_SPEECH_CORRECTIONS.items():
        if wrong in text.lower():
            text = text.replace(wrong, right)
    return text


class VoiceFirstBackend:
    """Backend voice-first system integrated with JARVIS planner."""

    def __init__(self):
        self.state = "passive"
        self.conversation_active = False
        self.last_active_time = 0.0
        self._wake_model = None
        self._cmd_model = None
        self._plan_history: list[Dict[str, Any]] = []
        self._plan_lock = None
        self._fast_plan_cache: Dict[str, str] = {}
        self._last_metrics: Dict[str, Any] = {}

    def init_models(self, wake_model=None, cmd_model=None):
        self._wake_model = wake_model
        self._cmd_model = cmd_model

    def is_voice_active(self) -> bool:
        return self.conversation_active

    def get_voice_state(self) -> str:
        return self.state

    def process_text(self, text: str, planner_func=None) -> Dict[str, Any]:
        """Process voice input and return a structured result."""
        if not text or not text.strip():
            return {"action": "noop", "response": ""}

        text = text.strip()
        text = correct_speech(text)
        lower = text.lower()

        # Dismissal check
        if self.conversation_active and any(p in lower for p in DISMISS_PHRASES):
            self.conversation_active = False
            self.state = "passive"
            return {"action": "dismissal", "response": "Goodbye, sir."}

        # Fast command detection
        fast_result = self._check_fast_command(text)
        if fast_result:
            return fast_result

        # Wake word check
        if not self.conversation_active:
            if any(w in lower for w in WAKE_WORDS):
                self.conversation_active = True
                self.state = "active"
                self.last_active_time = time.time()
                if planner_func:
                    result = planner_func("")
                    return {"action": "wake", "response": "Systems online, sir. Awaiting instructions."}
                return {"action": "wake", "response": "Systems online, sir."}
            return {"action": "ignored", "response": ""}

        # Active conversation mode
        self.last_active_time = time.time()
        if planner_func:
            plan = planner_func(text)
            self._plan_history.append({"text": text, "plan": plan, "ts": time.time()})
            return {"action": "planner", "text": text, "plan": plan}

        return {"action": "ai_chat", "text": text}

    def _check_fast_command(self, text: str) -> Optional[Dict[str, Any]]:
        lower = text.lower()

        # Keyword pre-filter (O(1))
        if not any(kw in lower for kw in FAST_COMMAND_KEYWORDS):
            return None

        # Regex pattern matching
        for pattern, action in FAST_COMMAND_PATTERNS:
            m = pattern.search(lower)
            if m:
                if action == "play_in_app":
                    query = m.group(1).strip()
                    app = m.group(2).strip()
                    return {
                        "action": "search_in_app_v2",
                        "query": query,
                        "app": app,
                        "response": f"Searching for {query} in {app}, sir.",
                    }
                if action == "reminder":
                    return {
                        "action": "reminder",
                        "response": f"Reminder set for {text}, sir.",
                    }
                return {"action": action, "response": f"Executing: {text}, sir."}

        return None

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        """Return current system metrics for live widgets."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.1)
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            battery = psutil.sensors_battery()
            temps = psutil.sensors_temperatures()

            self._last_metrics = {
                "cpu": round(cpu, 1),
                "ram": round(mem.percent, 1),
                "ram_used": round(mem.used / (1024 ** 3), 1),
                "ram_total": round(mem.total / (1024 ** 3), 1),
                "disk_used": round(disk.used / (1024 ** 3), 1),
                "disk_total": round(disk.total / (1024 ** 3), 1),
                "disk_pct": round(disk.percent, 1),
                "net_up": round(net.bytes_sent / (1024 ** 2), 1),
                "net_down": round(net.bytes_recv / (1024 ** 2), 1),
                "battery_pct": battery.percent if battery else None,
                "battery_charging": battery.power_plugged if battery else None,
                "temps": {k: v[0].current if v else None for k, v in temps.items()},
            }
        except Exception as e:
            logger.warning("Metrics collection failed: %s", e)
            self._last_metrics = {"error": str(e)}

        return self._last_metrics


_voice_backend = VoiceFirstBackend()


def get_voice_backend() -> VoiceFirstBackend:
    return _voice_backend


def set_voice_backend(vb: VoiceFirstBackend) -> None:
    global _voice_backend
    _voice_backend = vb


def process_text(text: str, planner_func=None) -> Dict[str, Any]:
    return _voice_backend.process_text(text, planner_func)


def get_metrics_snapshot() -> Dict[str, Any]:
    return _voice_backend.get_metrics_snapshot()