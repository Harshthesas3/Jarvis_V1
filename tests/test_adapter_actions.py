import sys
import os
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.execution.adapter import ADAPTER_ACTIONS
from jarvis.types import TaskNode

class TestAdapterActions(unittest.TestCase):
    def test_all_actions_registered(self):
        self.assertIn("open_app", ADAPTER_ACTIONS)
        self.assertIn("system_stats", ADAPTER_ACTIONS)
        self.assertIn("time", ADAPTER_ACTIONS)
        self.assertIn("wait", ADAPTER_ACTIONS)
        self.assertIn("calendar_event", ADAPTER_ACTIONS)

    def test_system_stats_handler(self):
        handler = ADAPTER_ACTIONS["system_stats"]
        node = TaskNode(id="t1", action="system_stats")
        res = handler(node, {})
        self.assertIn("CPU utilization", res)

    def test_not_supported_handler(self):
        handler = ADAPTER_ACTIONS["calendar_event"]
        node = TaskNode(id="t2", action="calendar_event")
        res = handler(node, {})
        self.assertIn("not currently available", res)

if __name__ == "__main__":
    unittest.main()
