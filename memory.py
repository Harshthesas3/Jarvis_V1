"""
memory.py
---------
Persistent fact store for JARVIS. Backed by a single JSON file on disk.

Public API:
    load() -> dict
    save(data: dict) -> None

The on-disk shape is {"facts": [str, ...]}. Functions are deliberately small
and dependency-free so they can be called from the executor (which imports
this lazily) and from the planner context builder.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

MEMORY_FILE = "memory.json"


def _empty() -> Dict[str, Any]:
    return {"facts": []}


def load() -> Dict[str, Any]:
    """Read the memory file. Returns {"facts": []} if the file is missing
    or unparseable."""
    if not os.path.exists(MEMORY_FILE):
        return _empty()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty()

    if not isinstance(data, dict):
        return _empty()
    facts = data.get("facts", [])
    if not isinstance(facts, list):
        facts = []
    return {"facts": [str(f) for f in facts]}


def save(data: Dict[str, Any]) -> None:
    """Write the memory dict to disk atomically-ish (write+replace)."""
    payload = _empty()
    if isinstance(data, dict):
        facts = data.get("facts", [])
        if isinstance(facts, list):
            payload["facts"] = [str(f) for f in facts]
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
    except OSError:
        # Best-effort persistence; never raise into a TTS path.
        pass
