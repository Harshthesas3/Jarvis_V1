"""
speech_correction.py
--------------------
Post-processing for speech-to-text output. Applies a configurable correction
dictionary to fix common transcription errors before the text reaches the
planner.

Public API:
    correct(text: str) -> str
    add_correction(wrong: str, right: str) -> None
    load_corrections(path: str) -> None
"""

from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger("jarvis.speech")

CORRECTIONS: dict[str, str] = {
    "fellow world": "hello world",
    "fellow": "hello",
    "python project": "Python Projects",
    "python projects": "Python Projects",
    "v s code": "VS Code",
    "vscode": "VS Code",
    "micro soft": "Microsoft",
    "micro soft store": "Microsoft Store",
    "power point": "PowerPoint",
    "note pad": "Notepad",
    "calc": "calculator",
    "calc you later": "calculator",
    "down loads": "Downloads",
    "documents": "Documents",
    "desk top": "Desktop",
    "descant": "Desktop",
    "re cycle": "Recycle Bin",
    "task manager": "Task Manager",
    "control panel": "Control Panel",
    "device manager": "Device Manager",
    "re gedit": "Registry Editor",
    "cmd": "Command Prompt",
    "power shell": "Windows PowerShell",
    "whats app": "WhatsApp",
    "you tube": "YouTube",
    "chat g p t": "ChatGPT",
    "chat gpt": "ChatGPT",
    "g mail": "Gmail",
    "goo gle": "Google",
    "pen apple music": "open Apple Music",
    "when apple music": "open Apple Music",
    "run microsoft store": "open Microsoft Store",
    "launch microsoft store": "open Microsoft Store",
    "start microsoft store": "open Microsoft Store",
    "pen chrome": "open Chrome",
    "when chrome": "open Chrome",
    "go to": "go to",
    "set up": "setup",
    "log in": "login",
    "log out": "log off",
    "create file": "create file",
    "delete file": "delete file",
    "rename file": "rename file",
    "copy file": "copy file",
    "move file": "move file",
    "read file": "read file",
    "write file": "write file",
    "new folder": "new folder",
    "open folder": "open folder",
    "search for": "search for",
    "look up": "look up",
    "type text": "type text",
    "press key": "press key",
    "scroll down": "scroll down",
    "scroll up": "scroll up",
    "double click": "double click",
    "right click": "right click",
    "take a screenshot": "take a screenshot",
    "set volume": "set volume",
    "remind me": "remind me",
    "create reminder": "create reminder",
    "generate code": "generate code",
    "write code": "write code",
    "focus on": "focus on",
    "wait for": "wait for",
    "switch to": "switch to",
    "close app": "close app",
    "open app": "open app",
}


def correct(text: str) -> str:
    if not text:
        return text or ""
    result = text
    for wrong, right in CORRECTIONS.items():
        result = re.sub(
            r"(?<![a-zA-Z])" + re.escape(wrong) + r"(?![a-zA-Z])",
            right,
            result,
            flags=re.IGNORECASE,
        )
    return result


def add_correction(wrong: str, right: str) -> None:
    CORRECTIONS[wrong.strip()] = right.strip()


def load_corrections(path: str) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            CORRECTIONS[k.strip()] = v.strip()
        logger.info("Loaded %d corrections from %s", len(data), path)
    except Exception as exc:
        logger.warning("Failed to load corrections from %s: %s", path, exc)
