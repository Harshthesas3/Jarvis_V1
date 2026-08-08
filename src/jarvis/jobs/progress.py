"""Progress tracking for background jobs."""

from __future__ import annotations

from typing import Dict, Optional

from jarvis.jobs.model import Job, JobStatus
from jarvis.jobs.store import JobStore


class ProgressTracker:
    """Tracks progress of background jobs using the JobStore."""

    def __init__(self, store: JobStore) -> None:
        self._store = store

    def get_job_progress(self, job_id: str) -> Optional[float]:
        """Get the progress of a specific job.

        Returns None if the job is not found.
        """
        job = self._store.get(job_id)
        if job is None:
            return None
        return job.progress

    def get_all_jobs_progress(self) -> Dict[str, float]:
        """Get progress for all non-terminal jobs.

        Returns a dictionary mapping job_id to progress (0.0-100.0).
        """
        active_statuses = [s for s in JobStatus if not s.terminal]
        jobs = []
        for status in active_statuses:
            jobs.extend(self._store.list(status=status))
        return {job.job_id: job.progress for job in jobs}

    def get_average_progress(self) -> float:
        """Get the average progress across all non-terminal jobs.

        Returns 0.0 if there are no active jobs.
        """
        progress_dict = self.get_all_jobs_progress()
        if not progress_dict:
            return 0.0
        return sum(progress_dict.values()) / len(progress_dict)