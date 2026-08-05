"""Tests for Phase 12: LatencyCollector telemetry."""

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.telemetry import LatencyCollector, STAGES  # noqa: E402


class TestLatencyCollector(unittest.TestCase):

    def _fresh(self):
        tmp = tempfile.mktemp(suffix=".jsonl")
        return LatencyCollector(output_path=tmp), tmp

    def test_record_and_finish_turn(self):
        col, path = self._fresh()
        col.start_turn()
        col.record("stt", 0.250)
        col.record("llm", 0.800)
        rec = col.finish_turn()
        self.assertAlmostEqual(rec["stt_ms"], 250.0, delta=5)
        self.assertAlmostEqual(rec["llm_ms"], 800.0, delta=5)
        self.assertIn("total_ms", rec)
        self.assertIn("timestamp", rec)

    def test_measure_context_manager(self):
        col, path = self._fresh()
        col.start_turn()
        with col.measure("tts"):
            time.sleep(0.05)
        rec = col.finish_turn()
        self.assertGreaterEqual(rec["tts_ms"], 45)

    def test_start_end_stage(self):
        col, path = self._fresh()
        col.start_turn()
        col.start_stage("intent")
        time.sleep(0.02)
        col.end_stage("intent")
        rec = col.finish_turn()
        self.assertGreaterEqual(rec["intent_ms"], 15)

    def test_persistence_to_jsonl(self):
        col, path = self._fresh()
        col.start_turn()
        col.record("wake", 0.100)
        col.finish_turn({"label": "test"})
        # File should exist and contain valid JSON
        with open(path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data["wake_ms"], 100.0)
        self.assertEqual(data["label"], "test")

    def test_read_all_returns_records(self):
        col, path = self._fresh()
        for _ in range(3):
            col.start_turn()
            col.record("stt", 0.2)
            col.finish_turn()
        records = col.read_all()
        self.assertEqual(len(records), 3)

    def test_summarize_computes_stats(self):
        col, path = self._fresh()
        for ms in [100, 200, 300]:
            col.start_turn()
            col.record("stt", ms / 1000.0)
            col.finish_turn()
        summary = col.summarize()
        self.assertIn("stt_ms", summary)
        s = summary["stt_ms"]
        self.assertEqual(s["samples"], 3)
        self.assertAlmostEqual(s["mean_ms"], 200.0, delta=2)

    def test_extra_fields_in_turn(self):
        col, path = self._fresh()
        col.start_turn()
        rec = col.finish_turn({"action": "ai_chat"})
        self.assertEqual(rec["action"], "ai_chat")

    def test_stages_constant_is_complete(self):
        for stage in ["wake", "recording", "stt", "intent", "memory", "llm", "tts", "playback"]:
            self.assertIn(stage, STAGES)


if __name__ == "__main__":
    unittest.main()
