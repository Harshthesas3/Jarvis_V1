"""Tests for Phase 11: ProjectStateMemory."""

import os
import sys
import time
import tempfile
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.memory.project_state import ProjectStateMemory  # noqa: E402


class TestProjectStateMemoryStandalone(unittest.TestCase):
    """Tests that run without a job service or workspace manager."""

    def setUp(self):
        self.mem = ProjectStateMemory()

    def test_active_project_set_get(self):
        self.assertIsNone(self.mem.get_active_project())
        self.mem.set_active_project("SpotifyClone")
        self.assertEqual(self.mem.get_active_project(), "SpotifyClone")

    def test_active_project_overwrite(self):
        self.mem.set_active_project("ProjectA")
        self.mem.set_active_project("ProjectB")
        self.assertEqual(self.mem.get_active_project(), "ProjectB")

    def test_context_block_empty_when_no_data(self):
        block = self.mem.build_context_block()
        # No active project, no job service → empty string
        self.assertEqual(block, "")

    def test_context_block_with_active_project(self):
        self.mem.set_active_project("MyApp")
        block = self.mem.build_context_block()
        self.assertIn("MyApp", block)

    def test_deduplication_detects_same_response(self):
        self.mem.is_duplicate_response("Hello sir.")  # first time → not dup
        result = self.mem.is_duplicate_response("Hello sir.")
        self.assertTrue(result)

    def test_deduplication_different_responses(self):
        self.mem.is_duplicate_response("Hello sir.")
        result = self.mem.is_duplicate_response("Goodbye sir.")
        self.assertFalse(result)

    def test_clear_dedupe_resets(self):
        self.mem.is_duplicate_response("Hello sir.")
        self.mem.clear_dedupe()
        result = self.mem.is_duplicate_response("Hello sir.")
        self.assertFalse(result)

    def test_empty_job_list_without_service(self):
        self.assertEqual(self.mem.active_jobs(), [])

    def test_empty_projects_without_manager(self):
        self.assertEqual(self.mem.known_projects(), [])


class TestProjectStateMemoryWithStubs(unittest.TestCase):
    """Tests using lightweight stubs for job service and workspace manager."""

    def _make_stub_job(self, kind, status, progress, message=""):
        class _J:
            def to_dict(self_):
                return {"kind": kind, "status": status, "progress": progress, "message": message}
        return _J()

    def test_active_jobs_from_service(self):
        class _Service:
            def active(self):
                return [self._make_stub_job("build_project", "running", 42.0, "Building")]
            def _make_stub_job(self_, *a, **kw):
                class J:
                    def to_dict(self__):
                        return {"kind": a[0], "status": a[1], "progress": a[2], "message": a[3] if len(a) > 3 else ""}
                return J()
        svc = _Service()
        mem = ProjectStateMemory(job_service=svc)
        jobs = mem.active_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["kind"], "build_project")

    def test_context_block_includes_jobs(self):
        class _Service:
            def active(self):
                class J:
                    def to_dict(self_):
                        return {"kind": "build_project", "status": "running", "progress": 55.0, "message": "Compiling"}
                return [J()]
        mem = ProjectStateMemory(job_service=_Service())
        block = mem.build_context_block()
        self.assertIn("Running jobs", block)
        self.assertIn("build_project", block)


if __name__ == "__main__":
    unittest.main()
