"""Multi-step clause splitting utilities."""

from __future__ import annotations

import re

# Verb prefix for boundary detection
_VERB_PREFIX = (
    r"(?:please\s+)?"
    r"(?:open|launch|start|run|close|quit|exit|switch|go|create|make|"
    r"read|write|append|add|delete|rename|move|copy|search|remind|set|"
    r"play|pause|stop|next|previous|skip|lock|shutdown|restart|take|"
    r"capture|describe|analyze|explain|summarize|remember|recall|forget|"
    r"clear|show|list|add|schedule|tell|message|email|draft|send|volume|"
    r"save|put|log|sign|power|reboot|type|press|scroll|click|double|"
    r"right|run|execute|generate|wait)"
)


def _split_on_boundary_words(t: str) -> list[str]:
    DELIM = "\x00"
    for pat in [
        r"\band\s+then\b",
        r"\bthen\s+after\s+that\b",
        r"\bafter\s+that\b",
        r"\bnext\b",
        r"\balso\b",
        r"\bfinally\b",
        r"\bfollowed\s+by\b",
        r"\bplus\b",
    ]:
        t = re.sub(pat, DELIM, t, flags=re.IGNORECASE)
    for pat in [
        r"\band\b(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press|scroll|click|double|right|run|execute|generate|wait))",
        r"\bthen\b(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press|scroll|click|double|right|run|execute|generate|wait))",
    ]:
        t = re.sub(pat, DELIM, t, flags=re.IGNORECASE)
    return [c.strip() for c in t.split(DELIM) if c.strip()]


def split_clauses(text: str) -> list[str]:
    """Split text into clauses based on commas, semicolons, and boundary words."""
    DELIM = "\x00"
    # First split on commas and semicolons, but only if the part after looks like a command
    raw_parts = re.split(r"\s*[,;]\s*", text)
    parts: list[str] = []
    for i, part in enumerate(raw_parts):
        if i == 0:
            parts.append(part)
        else:
            # Check if this part starts like a command
            if re.match(_VERB_PREFIX, part.strip(), re.IGNORECASE):
                parts.append(part)
            else:
                # Not a command, merge with previous part
                parts[-1] = parts[-1] + ", " + part
    # Now split each part on boundary words
    result: list[str] = []
    for part in parts:
        result.extend(_split_on_boundary_words(part))
    # Clean leading boundary words from each clause
    cleaned: list[str] = []
    for clause in result:
        c = re.sub(
            r"^(?:\s*(?:and\s+then|then\s+after\s+that|after\s+that|then|and|also|finally|next|plus)\s+)+",
            "",
            clause,
            flags=re.IGNORECASE,
        ).strip()
        if c:
            cleaned.append(c)
    return cleaned