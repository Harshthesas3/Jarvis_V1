"""Tests for EventBus subscribers."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.eventbus.bus import InMemoryEventBus
from jarvis.eventbus.events import COMMAND_RECEIVED, WAKE_WORD_DETECTED
from jarvis.eventbus.subscribers import SystemLogSubscriber, TelemetrySubscriber
from jarvis.interfaces.events import EventPriority, SystemEvent


class TestEventSubscribers(unittest.TestCase):

    def test_telemetry_subscriber_logs_all_events(self):
        tmp_dir = tempfile.mkdtemp()
        log_path = os.path.join(tmp_dir, "events.log")
        sub = TelemetrySubscriber(output_path=log_path)

        bus = InMemoryEventBus()
        bus.subscribe_all(sub.handle_event)

        ev1 = SystemEvent(type=WAKE_WORD_DETECTED, source="test")
        ev2 = SystemEvent(type=COMMAND_RECEIVED, source="test", data={"text": "hello"})

        bus.publish(ev1)
        bus.publish(ev2)

        with open(log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["type"], WAKE_WORD_DETECTED)
        self.assertEqual(lines[1]["data"]["text"], "hello")

    def test_system_log_subscriber_registration(self):
        sub = SystemLogSubscriber()
        subs = sub.get_subscriptions()
        self.assertIn(WAKE_WORD_DETECTED, subs)
        self.assertIn(COMMAND_RECEIVED, subs)


if __name__ == "__main__":
    unittest.main()
