import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.jobs.model import Job, JobStatus  # noqa: E402
from jarvis.opencode.session import (  # noqa: E402
    OpencodeSession,
    infer_progress,
    run_opencode_build,
)
from jarvis.workspace.manager import WorkspaceManager  # noqa: E402

FAKE_SCRIPT = """import sys, time
print("Planning the build")
time.sleep(0.2)
print("Writing modules 50%")
time.sleep(0.2)
print("Running tests")
print("Done.")
sys.exit(0)
"""

FAIL_SCRIPT = """import sys
print("Something failed")
sys.exit(3)
"""


class RecordingBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)

    def publish_async(self, event):
        self.events.append(event)


def _write_script(text, dir_path=None):
    parent = dir_path or tempfile.mkdtemp()
    fd, path = tempfile.mkstemp(suffix=".py", dir=parent)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestInferProgress(unittest.TestCase):
    def test_percentage(self):
        self.assertEqual(infer_progress("building 50% done"), 50.0)
        self.assertEqual(infer_progress("120%?"), 95.0)

    def test_keyword_hints(self):
        self.assertEqual(infer_progress("Planning the build"), 20.0)
        self.assertEqual(infer_progress("Writing modules"), 45.0)
        self.assertEqual(infer_progress("Running tests"), 70.0)
        self.assertEqual(infer_progress("Done."), 90.0)
        self.assertIsNone(infer_progress("random line"))


class TestOpencodeSession(unittest.TestCase):
    def test_streams_and_exits(self):
        script = _write_script(FAKE_SCRIPT)
        tmp = tempfile.mkdtemp()
        session = OpencodeSession(tmp, "build app", binary=sys.executable, extra_args=[script])
        session.start()
        collected = []
        while session.running:
            collected.extend(session.poll_lines())
            __import__("time").sleep(0.02)
        collected.extend(session.poll_lines())
        rc = session.wait()
        self.assertEqual(rc, 0)
        text = "\n".join(collected)
        self.assertIn("Planning the build", text)
        self.assertIn("Done.", text)

    def test_missing_binary_raises(self):
        tmp = tempfile.mkdtemp()
        session = OpencodeSession(tmp, "x", binary="definitely_not_a_real_binary_xyz")
        with self.assertRaises(RuntimeError):
            session.start()


class TestRunOpencodeBuild(unittest.TestCase):
    def setUp(self):
        self.tmp_root = tempfile.mkdtemp()
        self.script_dir = tempfile.mkdtemp()
        self.script = _write_script(FAKE_SCRIPT, dir_path=self.script_dir)
        self.fail_script = None
        self.bus = RecordingBus()

    def tearDown(self):
        for p in (self.script, self.fail_script):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _reporter(self):
        calls = []

        def rep(progress, msg=None):
            calls.append((progress, msg))

        return rep, calls

    def test_success_flow(self):
        job = Job(job_id="b1", kind="opencode_build", params={"name": "FakeApp", "description": "A test app"})
        report, calls = self._reporter()
        result = run_opencode_build(
            job,
            report,
            event_bus=self.bus,
            workspace_manager=WorkspaceManager(project_root=self.tmp_root),
            opencode_binary=sys.executable,
            opencode_args=[self.script],
        )
        self.assertEqual(result["status"], "completed")
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_root, "FakeApp")))
        progress = WorkspaceManager(project_root=self.tmp_root).read_progress(job.workspace)
        self.assertEqual(progress["status"], "completed")
        self.assertEqual(progress["progress"], 100.0)
        self.assertTrue(any(calls), "expected at least one progress report")
        types = [e.type for e in self.bus.events]
        self.assertIn("project.opencode_launched", types)
        self.assertIn("project.opencode_completed", types)
        self.assertEqual(job.status, JobStatus.QUEUED)

    def test_failure_flow(self):
        self.fail_script = _write_script(FAIL_SCRIPT, dir_path=self.script_dir)
        job = Job(job_id="b2", kind="opencode_build", params={"name": "BadApp"})
        report, _ = self._reporter()
        result = run_opencode_build(
            job,
            report,
            event_bus=self.bus,
            workspace_manager=WorkspaceManager(project_root=self.tmp_root),
            opencode_binary=sys.executable,
            opencode_args=[self.fail_script],
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 3)
        types = [e.type for e in self.bus.events]
        self.assertIn("project.opencode_failed", types)


if __name__ == "__main__":
    unittest.main()