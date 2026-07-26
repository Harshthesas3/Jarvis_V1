"""Planner configuration — constants, model name, and supported actions.

All values are exported at module level.  The planner model name is resolved
lazily (at function-call time) to avoid import-time coupling with the settings
system.
"""

from __future__ import annotations

import sys
from typing import FrozenSet

from jarvis.types import (
    CIRCUIT_BREAKER_MAX_FAILURES,
    CIRCUIT_BREAKER_RESET_SECONDS,
    CONFIDENCE_THRESHOLD,
    LLM_RETRY_DELAY_MS,
    LLM_TIMEOUT_SECONDS,
    MAX_INPUT_LENGTH,
    MAX_LLM_RETRIES,
    MAX_STEPS,
)

__all__ = [
    "MAX_INPUT_LENGTH",
    "CONFIDENCE_THRESHOLD",
    "MAX_STEPS",
    "MAX_LLM_RETRIES",
    "LLM_RETRY_DELAY_MS",
    "LLM_TIMEOUT_SECONDS",
    "CIRCUIT_BREAKER_MAX_FAILURES",
    "CIRCUIT_BREAKER_RESET_SECONDS",
    "DEFAULT_PLANNER_MODEL",
    "get_planner_model",
    "SUPPORTED_ACTIONS",
]

# ---------------------------------------------------------------------------
# Default model name (fallback when settings_manager is unavailable)
# ---------------------------------------------------------------------------

DEFAULT_PLANNER_MODEL: str = "qwen3.5:4b"

_PLANNER_MODEL_CACHE: str | None = None


def get_planner_model() -> str:
    """Return the configured planner model name.

    Attempts to read ``models.planner_model`` from the settings manager
    (which itself reads ``config.json``).  Falls back to
    ``DEFAULT_PLANNER_MODEL`` when the settings manager is not installed or
    the key is missing.

    The settings module is imported lazily so that ``config.py`` can be
    imported without triggering a full settings load at import time.
    """
    global _PLANNER_MODEL_CACHE  # noqa: PLW0603
    if _PLANNER_MODEL_CACHE is not None:
        return _PLANNER_MODEL_CACHE

    if "settings_manager" in sys.modules or _settings_manager_available():
        try:
            from settings_manager import settings  # type: ignore[import-untyped]

            model = settings.get("models.planner_model", DEFAULT_PLANNER_MODEL)
            _PLANNER_MODEL_CACHE = model
            return model
        except Exception:
            pass

    _PLANNER_MODEL_CACHE = DEFAULT_PLANNER_MODEL
    return DEFAULT_PLANNER_MODEL


def _settings_manager_available() -> bool:
    """Return ``True`` if the settings_manager module can be imported."""
    try:
        __import__("settings_manager")
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Supported actions  (mirrors planner.py lines 337-385)
# ---------------------------------------------------------------------------

SUPPORTED_ACTIONS: FrozenSet[str] = frozenset({
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
    "open_folder",
})
