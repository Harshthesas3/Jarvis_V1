"""Telemetry and logging event bus subscribers."""

import json
import logging
import os
import time
from jarvis.interfaces.events import EventSubscriber, SystemEvent, EventPriority

logger = logging.getLogger("jarvis.eventbus.subscribers")

_DEFAULT_EVENT_LOG = os.path.join(os.getcwd(), "data", "events.log")


class TelemetrySubscriber(EventSubscriber):
    """Subscribes to all events and appends them as JSON lines to data/events.log."""

    def __init__(self, output_path: str | None = None) -> None:
        self._path = output_path or _DEFAULT_EVENT_LOG
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def handle_event(self, event: SystemEvent) -> None:
        rec = {
            "timestamp": time.time(),
            "type": event.type,
            "source": event.source,
            "priority": event.priority.name if hasattr(event.priority, "name") else str(event.priority),
            "data": event.data,
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Could not write event log: %s", exc)

    def get_subscriptions(self) -> dict:
        return {}


class SystemLogSubscriber(EventSubscriber):
    """Subscribes to key lifecycle events and logs human-readable summary lines."""

    def __init__(self) -> None:
        pass

    def on_wake(self, event: SystemEvent) -> None:
        logger.info("⚡ [EVENT] Wake word detected from %s", event.source)

    def on_command(self, event: SystemEvent) -> None:
        text = event.data.get("text", "")
        logger.info("🎤 [EVENT] Command received: '%s'", text)

    def on_plan(self, event: SystemEvent) -> None:
        logger.info("🧠 [EVENT] Planning started: %s", event.data.get("text", ""))

    def on_job_started(self, event: SystemEvent) -> None:
        logger.info("⚙️ [EVENT] Job started: %s", event.data.get("job_id", ""))

    def on_job_completed(self, event: SystemEvent) -> None:
        logger.info("✅ [EVENT] Job completed: %s", event.data.get("job_id", ""))

    def on_job_failed(self, event: SystemEvent) -> None:
        logger.warning("❌ [EVENT] Job failed: %s - %s", event.data.get("job_id", ""), event.data.get("error", ""))

    def get_subscriptions(self) -> dict:
        from jarvis.eventbus import events as ev
        return {
            ev.WAKE_WORD_DETECTED: self.on_wake,
            ev.COMMAND_RECEIVED: self.on_command,
            ev.PLANNING_STARTED: self.on_plan,
            ev.JOB_STARTED: self.on_job_started,
            ev.JOB_COMPLETED: self.on_job_completed,
            ev.JOB_FAILED: self.on_job_failed,
        }
