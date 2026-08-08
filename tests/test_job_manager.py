import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.jobs.model import Job, JobStatus
from jarvis.jobs.queue import BackgroundJobQueue
from jarvis.jobs.store import JobStore
from jarvis.jobs.manager import JobManager


class TestJobManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = JobStore(os.path.join(self.tmp, "jobs.db"))
        self.queue = BackgroundJobQueue(self.store, workers=2)
        self.manager = JobManager(self.store, self.queue)
        self.results = []

    def tearDown(self):
        self.queue.shutdown(wait=True)
        self.store.close()

    def test_submit_job(self):
        def handler(job, report):
            report(50.0, "halfway")

        self.manager.register_handler("test", handler)
        job = self.manager.submit("test", {"param": 1})

        self.assertIsInstance(job, Job)
        self.assertEqual(job.kind, "test")
        self.assertEqual(job.params, {"param": 1})
        # The job may be queued or already running due to immediate execution
        self.assertIn(job.status, (JobStatus.QUEUED, JobStatus.RUNNING))

    def test_get_job(self):
        job = Job(job_id="test123", kind="test", params={})
        self.store.create(job)

        fetched = self.manager.get("test123")
        self.assertIsNotNone(fetched)
        if fetched is not None:
            self.assertEqual(fetched.job_id, "test123")

    def test_list_jobs(self):
        for i in range(3):
            job = Job(job_id=f"job{i}", kind="test")
            self.store.create(job)

        jobs = self.manager.list()
        self.assertEqual(len(jobs), 3)

    def test_active_jobs(self):
        # Add a queued job
        queued = Job(job_id="queued", kind="test")
        self.store.create(queued)
        # Add a completed job
        completed = Job(job_id="completed", kind="test", status=JobStatus.COMPLETED)
        self.store.create(completed)

        active = self.manager.active()
        # Should only return the queued job (non-terminal)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].job_id, "queued")

    def test_cancel_job(self):
        def handler(job, report):
            # Simulate long-running job
            while not job.cancel_event.is_set():
                time.sleep(0.01)

        self.manager.register_handler("cancel_test", handler)
        job = self.manager.submit("cancel_test")

        # Give it a moment to start
        time.sleep(0.1)
        self.assertTrue(self.manager.cancel(job.job_id))

        # Wait for termination
        deadline = time.time() + 1.0
        while time.time() < deadline:
            job = self.manager.get(job.job_id)
            if job is not None and job.status == JobStatus.CANCELLED:
                break
            time.sleep(0.01)

        self.assertEqual(job.status, JobStatus.CANCELLED)

    def test_supports(self):
        self.manager.register_handler("supported", lambda j, r: None)
        self.assertTrue(self.manager.supports("supported"))
        self.assertFalse(self.manager.supports("unsupported"))

    def test_shutdown(self):
        # Should not raise
        self.manager.shutdown()


if __name__ == "__main__":
    unittest.main()