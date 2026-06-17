"""
calendar_engine.py
------------------
Create .ics calendar events for JARVIS and open them with the OS handler.

Public API:
    create_calendar_event(title, date, time, duration_minutes=60) -> dict
    generate_ics(title, start_dt, duration_minutes=60, description="") -> str
    parse_when(text) -> Optional[datetime]    # re-uses reminders.parse_when

Output:
    CalendarEvents/<safe_title>_<timestamp>.ics
    The file is opened with the default .ics handler (Outlook / Windows
    Calendar / any registered client).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("jarvis.calendar")

EVENTS_DIR = "CalendarEvents"

# ---------------------------------------------------------------------------
# Date / time parsing
# ---------------------------------------------------------------------------
_DAY_WORDS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_TIME_RE = re.compile(
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?",
    re.IGNORECASE,
)


def _parse_clock(text: str) -> Optional[tuple[int, int]]:
    m = _TIME_RE.search(text)
    if not m:
        return None
    h = int(m.group("h"))
    minute = int(m.group("m") or 0)
    ampm = (m.group("ampm") or "").lower().replace(".", "")
    if ampm.startswith("p") and h < 12:
        h += 12
    elif ampm.startswith("a") and h == 12:
        h = 0
    if h > 23 or minute > 59:
        return None
    return h, minute


def _next_weekday(target: int) -> datetime:
    today = datetime.now()
    days_ahead = (target - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def parse_date(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse a (date, time) pair into an absolute datetime. If date_str is
    empty or None, assumes today. If time_str is empty, defaults to 9:00."""
    now = datetime.now()
    s = (date_str or "").strip().lower().replace(".", "")

    if not s or s == "today":
        base = now
    elif s == "tomorrow":
        base = now + timedelta(days=1)
    elif s in _DAY_WORDS:
        base = _next_weekday(_DAY_WORDS[s])
    else:
        # Try ISO date first, then "15 June 2026" / "15 June"
        base = None
        for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %B", "%B %d", "%B %d %Y",
                    "%d/%m/%Y", "%m/%d/%Y"):
            try:
                parsed = datetime.strptime(s, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=now.year)
                base = parsed
                break
            except ValueError:
                continue
        if base is None:
            return None

    clock = _parse_clock(time_str or "")
    if clock is None:
        clock = (9, 0)
    h, minute = clock
    return base.replace(hour=h, minute=minute, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# ICS generation (RFC 5545)
# ---------------------------------------------------------------------------
def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
            .replace(";", r"\;")
            .replace(",", r"\,")
            .replace("\n", r"\n")
    )


def generate_ics(
    title: str,
    start_dt: datetime,
    duration_minutes: int = 60,
    description: str = "",
) -> str:
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    uid = f"{int(start_dt.timestamp())}-{abs(hash(title)) % 10**8}@jarvis"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//JARVIS//Personal Assistant//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(title)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_ics_escape(description)}")
    lines += [
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ics_escape(title)}",
        "TRIGGER:-PT15M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    return "\r\n".join(lines)


# ---------------------------------------------------------------------------
# File handling
# ---------------------------------------------------------------------------
def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
    return cleaned[:60] or "event"


def create_calendar_event(
    title: str,
    date: str,
    time: str,
    duration_minutes: int = 60,
    description: str = "",
) -> dict:
    """Create a .ics file for the given event and open it. Returns a status
    dict suitable for TTS."""
    if not title:
        return {"ok": False, "error": "Event needs a title, sir."}
    start_dt = parse_date(date, time)
    if start_dt is None:
        return {"ok": False, "error": f"Could not parse date or time, sir."}

    os.makedirs(EVENTS_DIR, exist_ok=True)
    fname = f"{_safe_filename(title)}_{start_dt.strftime('%Y%m%d_%H%M')}.ics"
    path = os.path.join(EVENTS_DIR, fname)

    try:
        ics = generate_ics(title, start_dt, duration_minutes, description)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(ics)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to write .ics file")
        return {"ok": False, "error": f"Failed to write event, sir. {exc}"}

    opened = _open_file(path)
    human = start_dt.strftime("%A %d %B %Y at %I:%M %p")
    return {
        "ok": True,
        "path": path,
        "opened": opened,
        "title": title,
        "human_time": human,
        "duration_minutes": duration_minutes,
    }


def _open_file(path: str) -> bool:
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows-only
        return True
    except AttributeError:
        # Fallback for non-Windows (e.g. test environment)
        try:
            subprocess.Popen(["xdg-open", path])
            return True
        except Exception:
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not open %s: %s", path, exc)
        return False
