"""Intent classification — LLM-based understanding of user goals."""

from __future__ import annotations

import logging
from typing import Optional

from ..llm import extract_json, llm_chat_with_retry
from ..config import get_planner_model

logger = logging.getLogger("jarvis.planner.intent")

_INTENT_CLASSIFIER_PROMPT = """You are JARVIS, an intent classifier.

Your ONLY job: identify what the user wants to accomplish.

Output a JSON object with exactly these four fields:
- "intent": one of the following categories:
    "scheduling" — planning schedules, timetables, routines, organizing time
    "project_analysis" — analyzing code, finding files, understanding a project
    "memory" — remembering, recalling, or forgetting information
    "web_search" — searching the internet (not for personal advice)
    "communication" — sending WhatsApp messages or emails to specific people
    "file_management" — creating, reading, writing, deleting, renaming files/folders
    "app_control" — opening, closing, switching applications or windows
    "system_control" — locking, shutting down, restarting, sleeping, volume control
    "media_control" — playing, pausing, skipping music
    "time_date" — asking for the time or date
    "clipboard" — reading, writing, or clearing the clipboard
    "screenshot" — taking a screenshot
    "screen_awareness" — describing or analyzing what's on screen
    "diagnostics" — running system diagnostics
    "code_generation" — generating or writing code
    "terminal_command" — running a terminal/powerShell command
    "desktop_automation" — clicking, typing, pressing keys, scrolling
    "browser" — opening URLs or searching the browser
    "conversation" — general chat, greetings, opinions, jokes, casual talk

- "goal": a short phrase describing what the user wants to accomplish.
- "required_capabilities": a list of strings naming the capabilities needed.
- "confidence": a number between 0.0 and 1.0 indicating how certain you are.

CRITICAL RULES:
- NEVER output actions, plan steps, or parameters.
- NEVER use action names like "open_app", "web_search", "memory_store".
- ONLY output the four fields above.
- If unsure, set confidence < 0.5.

Output ONLY the JSON. No prose, no markdown, no actions."""


def classify_intent(user_text: str, planner_model: str) -> Optional[dict]:
    """Classify user intent. Returns {"intent", "goal", "confidence", "required_capabilities"}
    or None if classification fails. NEVER generates actions."""
    resp = llm_chat_with_retry(
        model=planner_model,
        messages=[
            {"role": "system", "content": _INTENT_CLASSIFIER_PROMPT},
            {"role": "user", "content": user_text},
        ],
        temperature=0.0,
        num_predict=200,
    )
    if resp is None:
        logger.warning("Intent classification failed (LLM unavailable)")
        return None
    try:
        raw = resp["message"]["content"]
        parsed = extract_json(raw)
        if parsed and isinstance(parsed, dict) and "intent" in parsed:
            return parsed
        logger.warning("Intent classification returned invalid JSON: %.200s", raw)
        return None
    except Exception as exc:
        logger.warning("Intent classification parsing failed: %s", exc)
        return None