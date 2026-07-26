import sys
import os
import unittest

# Ensure src and root are in path
sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.fast_command_router import FastCommandRouter, get_fast_router

class TestFastCommandRouter(unittest.TestCase):
    def setUp(self):
        self.router = FastCommandRouter()

    def test_time_command(self):
        res = self.router.route("what time is it")
        self.assertIsNotNone(res)
        self.assertEqual(res.get("action"), "time")
        self.assertIn("The time is", res.get("response", ""))

    def test_date_command(self):
        res = self.router.route("what is the date")
        self.assertIsNotNone(res)
        self.assertEqual(res.get("action"), "date")
        self.assertIn("Today is", res.get("response", ""))

    def test_volume_command(self):
        res = self.router.route("volume up")
        self.assertIsNotNone(res)
        self.assertEqual(res.get("action"), "volume_control")
        self.assertEqual(res.get("op"), "up")

    def test_screenshot_command(self):
        res = self.router.route("take screenshot")
        self.assertIsNotNone(res)
        self.assertEqual(res.get("action"), "screenshot")

    def test_non_fast_command(self):
        res = self.router.route("explain quantum physics to me")
        self.assertIsNone(res)

if __name__ == "__main__":
    unittest.main()
