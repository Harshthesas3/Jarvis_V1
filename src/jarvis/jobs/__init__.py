"""Background job system: persistent job store, queue, and service facade."""

from __future__ import annotations

from jarvis.jobs.model import Job, JobStatus
from jarvis.jobs.progress import ProgressTracker
from jarvis.jobs.queue import BackgroundJobQueue, JobHandler, ProgressReporter
from jarvis.jobs.manager import JobManager
from jarvis.jobs.service import JobService
from jarvis.jobs.store import JobStore

# Alias for backward compatibility and user-facing API
JobQueue = BackgroundJobQueue

__all__ = [
    "Job",
    "JobStatus",
    "BackgroundJobQueue",
    "JobHandler",
    "ProgressReporter",
    "JobService",
    "JobStore",
    "ProgressTracker",
    "JobQueue",
    "JobManager",
]
