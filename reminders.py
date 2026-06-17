"""
reminders.py
------------
Persistent reminder engine for JARVIS.

Public API:
    ReminderEngine  -- class. Singleton via get_engine().
    add_reminder(time_str, task) -> dict
    remove_reminder(index) -> bool
    list_reminders() -> list[dict]
    clear_reminders() -> int   (returns count cleared)
    start_checker(speak_fn)    -- spawns a background thread that fires reminders

Storage: reminders.json (UTF-8). Auto-load on construct, auto-save on any
mutation. Thread-safe via a single internal lock.

Time parsing: understands phrases like
    "tomorrow 4 pm", "tomorrow 4:30 pm",
    "today 8 pm", "tonight", "tonight at 9",
    "monday 10 am", "friday 4 pm",
    "8 pm", "20:00", "in 30 minutes".
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Optional

logger = logging.getLogger("jarvis.reminders")

STORE_FILE = "reminders.json"
CHECK_INTERVAL_SEC = 20  # How often the background thread wakes up
GRACE_SEC = 0            # No delay between due-time and firing


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Reminder:
    id: str
    task: str
    when_iso: str  # absolute ISO 8601 datetime
    created_iso: str
    completed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Reminder":
        return cls(
            id=str(d.get("id", "")),
            task=str(d.get("task", "")),
            when_iso=str(d.get("when_iso", "")),
            created_iso=str(d.get("created_iso", "")),
            completed=bool(d.get("completed", False)),
        )

    @property
    def when(self) -> datetime:
        try:
            return datetime.fromisoformat(self.when_iso)
        except Exception:
            return datetime.max


# ---------------------------------------------------------------------------
# Time parsing
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
    """Parse '4', '4pm', '4:30 pm', '20:00' into (hour, minute). 24h if no ampm."""
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
        days_ahead = 7  # always next week if today
    return today + timedelta(days=days_ahead)


def parse_when(text: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
    if not text:
        return None

    now = now or datetime.now()
    s = text.strip().lower().replace(".", "")

    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10
    }

    for word, value in number_words.items():
        s = s.replace(word, str(value))

    # in N minutes / hours
    m = re.search(
        r"in\s+(\d+)\s+(minute|minutes|min|hour|hours|hr|hrs)",
        s
    )
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = timedelta(hours=n) if "hour" in unit or "hr" in unit else timedelta(minutes=n)
        return now + delta

    base_date: Optional[datetime] = None
    if "tonight" in s:
        base_date = now
    elif "tomorrow" in s:
        base_date = now + timedelta(days=1)
    elif "today" in s:
        base_date = now
    else:
        for word, idx in _DAY_WORDS.items():
            if re.search(rf"\b{word}\b", s):
                base_date = _next_weekday(idx)
                break

    clock = _parse_clock(s)
    if clock is None and base_date is None:
        return None
    if base_date is None:
        base_date = now
    h, minute = clock if clock else (9, 0)
    candidate = base_date.replace(hour=h, minute=minute, second=0, microsecond=0)
    if candidate <= now and "tomorrow" not in s and "tonight" not in s:
        if base_date.date() == now.date() and clock is not None:
            candidate = candidate + timedelta(days=1)
        elif base_date.date() == now.date() and clock is None:
            candidate = candidate + timedelta(days=7)
    # For bare "tonight", if the resulting time is still in the past,
    # assume the user meant PM (e.g. "tonight at 9" -> 21:00, not 09:00).
    if "tonight" in s and candidate <= now and clock is not None and h < 12:
        candidate = candidate.replace(hour=h + 12)
    return candidate


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class ReminderEngine:
    def __init__(self, store_path: str = STORE_FILE) -> None:
        self.store_path = store_path
        self._lock = threading.Lock()
        self._reminders: List[Reminder] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._speak_fn: Optional[Callable[[str], None]] = None
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            self._reminders = []
            return
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._reminders = [Reminder.from_dict(d) for d in data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load reminders (%s); starting fresh.", exc)
            self._reminders = []

    def _save(self) -> None:
        tmp = self.store_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self._reminders], f, indent=2)
            os.replace(tmp, self.store_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to save reminders: %s", exc)

    def add_reminder(self, time_str: str, task: str) -> dict:
        when = parse_when(time_str)
        if when is None:
            return {"ok": False, "error": f"Could not understand time '{time_str}'."}
        rid = f"{int(time.time() * 1000)}-{len(self._reminders)}"
        rem = Reminder(
            id=rid,
            task=task.strip(),
            when_iso=when.isoformat(timespec="seconds"),
            created_iso=datetime.now().isoformat(timespec="seconds"),
        )
        with self._lock:
            self._reminders.append(rem)
            self._save()
        human = when.strftime("%A %d %B %Y at %I:%M %p")
        return {"ok": True, "reminder": rem.to_dict(), "human_time": human}

    def remove_reminder(self, index: int) -> bool:
        with self._lock:
            if 0 <= index < len(self._reminders):
                self._reminders.pop(index)
                self._save()
                return True
        return False

    def list_reminders(self) -> List[dict]:
        with self._lock:
            return [
                {
                    "index": i,
                    "task": r.task,
                    "when": r.when.strftime("%A %d %B %Y at %I:%M %p"),
                    "when_iso": r.when_iso,
                    "completed": r.completed,
                }
                for i, r in enumerate(self._reminders)
                if not r.completed
            ]

    def clear_reminders(self) -> int:
        with self._lock:
            n = len(self._reminders)
            self._reminders = []
            self._save()
            return n

    def start(self, speak_fn: Callable[[str], None]) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._speak_fn = speak_fn
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="JarvisReminderLoop", daemon=True
        )
        self._thread.start()
        logger.info("Reminder background thread started.")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._check_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Reminder check error: %s", exc)
            self._stop.wait(CHECK_INTERVAL_SEC)

    def _check_once(self) -> None:
        now = datetime.now()
        fired: List[int] = []
        with self._lock:
            for i, r in enumerate(self._reminders):
                if r.completed:
                    continue
                if r.when <= now + timedelta(seconds=GRACE_SEC):
                    r.completed = True
                    fired.append(i)
            if fired:
                self._save()
        for i in fired:
            rem = self._reminders[i] if i < len(self._reminders) else None
            if rem is None:
                continue
            msg = f"Reminder, sir: {rem.task}."
            print(f"\n[Reminder] {rem.task} (scheduled {rem.when_iso})")
            if self._speak_fn is not None:
                try:
                    self._speak_fn(msg)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Speak failed for reminder: %s", exc)


# ---------------------------------------------------------------------------
# Singleton accessor + module-level convenience
# ---------------------------------------------------------------------------
_engine: Optional[ReminderEngine] = None


def get_engine() -> ReminderEngine:
    global _engine
    if _engine is None:
        _engine = ReminderEngine()
    return _engine


def add_reminder(time_str: str, task: str) -> dict:
    return get_engine().add_reminder(time_str, task)


def remove_reminder(index: int) -> bool:
    return get_engine().remove_reminder(index)


def list_reminders() -> List[dict]:
    return get_engine().list_reminders()


def clear_reminders() -> int:
    return get_engine().clear_reminders()


def start_checker(speak_fn: Callable[[str], None]) -> None:
    get_engine().start(speak_fn)
