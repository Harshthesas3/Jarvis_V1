import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.jobs.model import Job, JobStatus  # noqa: E402
from jarvis.jobs.queue import BackgroundJobQueue  # noqa: E402
from jarvis.jobs.service import JobService  # noqa: E402
from jarvis.jobs.store import JobStore  # noqa: E402


class TestJobModel(unittest.TestCase):
    def test_round_trip(self):
        job = Job(job_id="abc", kind="test", params={"x": 1})
        restored = Job.from_dict(job.to_dict())
        self.assertEqual(restored.job_id, "abc")
        self.assertEqual(restored.kind, "test")
        self.assertEqual(restored.params, {"x": 1})
        self.assertEqual(restored.status, JobStatus.QUEUED)

    def test_terminal_status(self):
        self.assertTrue(JobStatus.COMPLETED.terminal)
        self.assertTrue(JobStatus.FAILED.terminal)
        self.assertFalse(JobStatus.RUNNING.terminal)

    def test_append_log_caps(self):
        job = Job(job_id="x", kind="k")
        for i in range(250):
            job.append_log(f"line {i}")
        self.assertEqual(len(job.logs), 200)


class TestJobStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = JobStore(os.path.join(self.tmp, "jobs.db"))

    def tearDown(self):
        self.store.close()

    def test_crud(self):
        job = Job(job_id="j1", kind="k", params={"a": 1}, workspace="C:\\Project\\X")
        self.store.create(job)
        fetched = self.store.get("j1")
        self.assertEqual(fetched.kind, "k")
        self.assertEqual(fetched.params, {"a": 1})
        self.assertEqual(fetched.workspace, "C:\\Project\\X")

        job.status = JobStatus.RUNNING
        job.progress = 50.0
        job.append_log("working")
        self.store.save(job)
        updated = self.store.get("j1")
        self.assertEqual(updated.status, JobStatus.RUNNING)
        self.assertEqual(updated.progress, 50.0)
        self.assertIn("working", updated.logs)

        self.store.delete("j1")
        self.assertIsNone(self.store.get("j1"))

    def test_list_and_count(self):
        for i in range(3):
            self.store.create(Job(job_id=f"job{i}", kind="k"))
        self.assertEqual(self.store.count(), 3)
        self.assertEqual(len(self.store.list()), 3)
        self.store.create(Job(job_id="done", kind="k", status=JobStatus.COMPLETED))
        self.assertEqual(len(self.store.list(status=JobStatus.COMPLETED)), 1)


class TestJobServiceIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = JobStore(os.path.join(self.tmp, "jobs.db"))
        self.queue = BackgroundJobQueue(self.store, workers=2)
        self.service = JobService(self.store, self.queue)
        self.results = []

    def tearDown(self):
        self.queue.shutdown(wait=True)
        self.store.close()

    def test_background_completion(self):
        def handler(job, report):
            report(10.0, "starting")
            time.sleep(0.1)
            report(60.0, "halfway")

        self.service.register_handler("demo", handler)
        job = self.service.submit("demo", {"x": 1})
        self.assertIn(job.status, (JobStatus.QUEUED, JobStatus.RUNNING))

        final = self._wait_terminal(job.job_id)
        self.assertEqual(final.status, JobStatus.COMPLETED)
        self.assertEqual(final.progress, 100.0)
        self.assertIn("halfway", final.logs)

    def test_missing_handler_fails(self):
        job = self.service.submit("no_such_kind")
        final = self._wait_terminal(job.job_id)
        self.assertEqual(final.status, JobStatus.FAILED)
        self.assertIn("no handler", final.error.lower())

    def test_cancel(self):
        def handler(job, report):
            report(5.0, "started")
            while not job.cancel_event.is_set():
                time.sleep(0.02)

        self.service.register_handler("slow", handler)
        job = self.service.submit("slow")
        time.sleep(0.1)
        self.assertTrue(self.service.cancel(job.job_id))
        final = self._wait_terminal(job.job_id)
        self.assertEqual(final.status, JobStatus.CANCELLED)

    def test_handler_exception_fails(self):
        def handler(job, report):
            raise ValueError("boom")

        self.service.register_handler("explode", handler)
        job = self.service.submit("explode")
        final = self._wait_terminal(job.job_id)
        self.assertEqual(final.status, JobStatus.FAILED)
        self.assertIn("boom", final.error)

    def _wait_terminal(self, job_id, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.store.get(job_id)
            if job is not None and job.status.terminal:
                return job
            time.sleep(0.02)
        self.fail(f"job {job_id} did not reach terminal state")


if __name__ == "__main__":
    unittest.main()