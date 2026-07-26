"""Folder alias resolution for path-based commands."""

from __future__ import annotations

import os
import re

_KNOWN_ALIASES: dict[str, str] = {}


def register_folder_alias(name: str, path: str) -> None:
    _KNOWN_ALIASES[name.lower().strip()] = path


def resolve_alias_path(text: str) -> str:
    """Resolve folder aliases (Downloads, Desktop, etc.) in a path string."""
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
        pattern = re.compile(r"(?<![\\/.\w])" + re.escape(alias) + r"(?![\\/.\w])", re.IGNORECASE)
        result = pattern.sub(lambda m: resolved, result)

    for alias, resolved in alias_map.items():
        _replacer(alias, resolved)
    for alias, resolved in _KNOWN_ALIASES.items():
        _replacer(alias, resolved)
    return result