"""Tests for StartupManager — concurrent pre-warming and readiness gates."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch


class TestStartupManagerReadiness(unittest.TestCase):
    """StartupManager state before and after prewarm."""

    def _make_manager(self):
        from jarvis.startup.manager import StartupManager
        return StartupManager()

    def test_all_not_ready_before_prewarm(self):
        """All subsystems report not-ready before prewarm_all() is called."""
        mgr = self._make_manager()
        for sub in ("whisper", "ollama", "piper", "chroma", "router", "opencode", "memory"):
            self.assertFalse(mgr.is_ready(sub), f"{sub} should not be ready before prewarm")

    def test_timeline_empty_before_prewarm(self):
        mgr = self._make_manager()
        self.assertEqual(mgr.get_timeline(), {})

    def test_wake_model_none_before_prewarm(self):
        mgr = self._make_manager()
        self.assertIsNone(mgr.wake_model)
        self.assertIsNone(mgr.cmd_model)
        self.assertIsNone(mgr.speaker)
        self.assertIsNone(mgr.fast_router)
        self.assertIsNone(mgr.opencode_path)


class TestStartupManagerPrewarm(unittest.TestCase):
    """StartupManager.prewarm_all() with all tasks mocked."""

    def _cfg(self, **overrides):
        defaults = {
            "models.stt_wake_model": "tiny",
            "models.stt_command_model": "distil-whisper/distil-small.en",
            "models.chat_model": "qwen3.5:4b",
            "paths.voice_model": "/fake/voice.onnx",
        }
        defaults.update(overrides)
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, default=None: defaults.get(key, default)
        return cfg

    def test_prewarm_marks_subsystems_ready(self):
        """After a mocked prewarm_all(), every subsystem is ready."""
        from jarvis.startup.manager import StartupManager

        mgr = StartupManager()

        # Replace all _prewarm_* methods with no-ops
        for sub in ("whisper", "ollama", "piper", "chroma", "router", "opencode", "memory"):
            setattr(mgr, f"_prewarm_{sub}", lambda *a, **kw: None)

        mgr.prewarm_all(self._cfg())

        for sub in ("whisper", "ollama", "piper", "chroma", "router", "opencode", "memory"):
            self.assertTrue(mgr.is_ready(sub), f"{sub} should be ready after mocked prewarm")

    def test_timeline_populated_after_prewarm(self):
        """get_timeline() returns subsystem entries with numeric ms values."""
        from jarvis.startup.manager import StartupManager

        mgr = StartupManager()
        for sub in ("whisper", "ollama", "piper", "chroma", "router", "opencode", "memory"):
            setattr(mgr, f"_prewarm_{sub}", lambda *a, **kw: None)

        mgr.prewarm_all(self._cfg())
        timeline = mgr.get_timeline()

        for sub in ("whisper", "ollama", "piper", "chroma", "router", "opencode", "memory"):
            self.assertIn(sub, timeline, f"{sub} should be in timeline")
            self.assertIsInstance(timeline[sub], float)

        self.assertIn("__total__", timeline)

    def test_prewarm_idempotent(self):
        """Calling prewarm_all() twice is a no-op on the second call."""
        from jarvis.startup.manager import StartupManager

        call_count = {"n": 0}

        def counting_task():
            call_count["n"] += 1

        mgr = StartupManager()
        for sub in ("whisper", "ollama", "piper", "chroma", "router", "opencode", "memory"):
            setattr(mgr, f"_prewarm_{sub}", counting_task)

        mgr.prewarm_all(self._cfg())
        first_count = call_count["n"]
        mgr.prewarm_all(self._cfg())  # second call — must be no-op

        self.assertEqual(call_count["n"], first_count, "Second prewarm_all() should not run tasks again")

    def test_failing_task_does_not_crash_others(self):
        """A prewarm task that raises must not prevent other subsystems from being ready."""
        from jarvis.startup.manager import StartupManager

        mgr = StartupManager()

        def explode():
            raise RuntimeError("simulated failure")

        # whisper fails; everything else is a no-op
        mgr._prewarm_whisper = lambda *a, **kw: explode()
        for sub in ("ollama", "piper", "chroma", "router", "opencode", "memory"):
            setattr(mgr, f"_prewarm_{sub}", lambda *a, **kw: None)

        mgr.prewarm_all(self._cfg())

        self.assertFalse(mgr.is_ready("whisper"), "Failed task must not be marked ready")
        for sub in ("ollama", "piper", "chroma", "router", "opencode", "memory"):
            self.assertTrue(mgr.is_ready(sub), f"{sub} should still be ready after whisper failure")

    def test_opencode_path_cached(self):
        """opencode_path is set after prewarm (may be None if binary not installed)."""
        from jarvis.startup.manager import StartupManager
        import shutil

        mgr = StartupManager()
        for sub in ("whisper", "ollama", "piper", "chroma", "router", "memory"):
            setattr(mgr, f"_prewarm_{sub}", lambda *a, **kw: None)

        # Let the real opencode prewarm run so we test the actual logic
        # It should set opencode_path to None (binary not in PATH in CI) or a string
        mgr.prewarm_all(self._cfg())

        # Regardless of whether opencode is installed, the attribute must be set
        # (is_ready("opencode") will be True; path may be None)
        self.assertTrue(mgr.is_ready("opencode"))
        # path is either None or a string — never a non-string
        self.assertIn(type(mgr.opencode_path), (str, type(None)))


class TestStartupManagerRunTask(unittest.TestCase):
    """_run_task timing and readiness bookkeeping."""

    def test_successful_task_sets_ready_and_timeline(self):
        from jarvis.startup.manager import StartupManager
        mgr = StartupManager()
        ran = []
        mgr._run_task("router", lambda: ran.append(True))
        self.assertTrue(mgr.is_ready("router"))
        self.assertIn("router", mgr.get_timeline())
        self.assertEqual(ran, [True])

    def test_failing_task_sets_not_ready(self):
        from jarvis.startup.manager import StartupManager
        mgr = StartupManager()

        def boom():
            raise ValueError("oops")

        mgr._run_task("piper", boom)
        self.assertFalse(mgr.is_ready("piper"))
        self.assertIn("piper", mgr.get_timeline())


class TestStartupTelemetry(unittest.TestCase):
    """StartupTelemetry persistence and comparison."""

    def _make_telemetry(self, tmp_path):
        from jarvis.startup.telemetry import StartupTelemetry
        return StartupTelemetry(output_path=str(tmp_path))

    def test_record_startup_writes_to_file(self):
        import tempfile, os, json
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            from jarvis.startup.telemetry import StartupTelemetry
            st = StartupTelemetry(output_path=path)
            timeline = {"whisper": 800.0, "ollama": 600.0, "__total__": 850.0}
            rec = st.record_startup(timeline, warm=False)
            self.assertEqual(rec["type"], "startup")
            self.assertFalse(rec["warm"])
            # File must exist and contain valid JSON line
            with open(path) as fh:
                line = fh.readline().strip()
            data = json.loads(line)
            self.assertEqual(data["type"], "startup")
        finally:
            os.unlink(path)

    def test_read_startup_records_filters_by_type(self):
        import tempfile, os, json
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
            # Write a mix of startup and turn records
            f.write(json.dumps({"type": "startup", "warm": False, "startup___total___ms": 2000.0}) + "\n")
            f.write(json.dumps({"type": "turn", "total_ms": 1500.0}) + "\n")
            f.write(json.dumps({"type": "startup", "warm": True, "startup___total___ms": 800.0}) + "\n")
        try:
            from jarvis.startup.telemetry import StartupTelemetry
            st = StartupTelemetry(output_path=path)
            recs = st.read_startup_records()
            self.assertEqual(len(recs), 2)
            for r in recs:
                self.assertEqual(r["type"], "startup")
        finally:
            os.unlink(path)

    def test_compare_cold_vs_warm_empty(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            from jarvis.startup.telemetry import StartupTelemetry
            st = StartupTelemetry(output_path=path)
            result = st.compare_cold_vs_warm()
            self.assertIsNone(result["cold"])
            self.assertIsNone(result["warm"])
        finally:
            os.unlink(path)


class TestGetStartupManagerSingleton(unittest.TestCase):
    """get_startup_manager() must return the same object every call."""

    def test_singleton_identity(self):
        # Reset the module-level singleton so this test is isolated
        import jarvis.startup.manager as mod
        original = mod._manager
        mod._manager = None
        try:
            from jarvis.startup.manager import get_startup_manager
            a = get_startup_manager()
            b = get_startup_manager()
            self.assertIs(a, b)
        finally:
            mod._manager = original


if __name__ == "__main__":
    unittest.main()
