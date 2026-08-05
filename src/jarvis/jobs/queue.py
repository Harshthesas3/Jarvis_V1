"""Background job queue with worker pool, progress reporting and cancellation."""

from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional

from jarvis.eventbus import events as ev
from jarvis.interfaces.events import EventBus, EventPriority, SystemEvent
from jarvis.jobs.model import Job, JobStatus
from jarvis.jobs.store import JobStore

logger = logging.getLogger("jarvis.jobs.queue")

ProgressReporter = Callable[[float, Optional[str]], None]
JobHandler = Callable[[Job, ProgressReporter], None]


class BackgroundJobQueue:
    """Runs registered job handlers on a worker pool.

    Handlers receive the job plus a progress reporter; the reporter
    persists state and publishes JOB_PROGRESS events. Long-running
    handlers cooperate with cancellation by polling ``job.cancel_event``.
    """

    def __init__(self, store: JobStore, event_bus: Optional[EventBus] = None, workers: int = 1) -> None:
        self._store = store
        self._event_bus = event_bus
        self._handlers: Dict[str, JobHandler] = {}
        self._running: Dict[str, Job] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="jarvis-job")

    def register(self, kind: str, handler: JobHandler) -> None:
        with self._lock:
            self._handlers[kind] = handler

    def unregister(self, kind: str) -> None:
        with self._lock:
            self._handlers.pop(kind, None)

    def supports(self, kind: str) -> bool:
        with self._lock:
            return kind in self._handlers

    def submit(self, job: Job) -> Job:
        self._store.save(job)
        self._publish(ev.JOB_QUEUED, job)
        self._executor.submit(self._run, job)
        return job

    def cancel(self, job_id: str) -> bool:
        job = self._store.get(job_id)
        if job is None or job.status.terminal:
            return False
        job.status = JobStatus.CANCELLING
        self._store.save(job)
        with self._lock:
            running = self._running.get(job_id)
        if running is not None:
            running.cancel_event.set()
        else:
            job.cancel_event.set()
        self._publish(ev.JOB_CANCELLED, job)
        return True

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    def _run(self, job: Job) -> None:
        with self._lock:
            handler = self._handlers.get(job.kind)
            self._running[job.job_id] = job
        if handler is None:
            self._finish(job, JobStatus.FAILED, error=f"No handler registered for kind '{job.kind}'")
            return

        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
        self._store.save(job)
        self._publish(ev.JOB_STARTED, job)

        try:
            handler(job, self._make_reporter(job))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s (%s) failed", job.job_id, job.kind)
            self._finish(job, JobStatus.FAILED, error=str(exc), trace=traceback.format_exc())
            return

        if job.is_cancelling:
            self._finish(job, JobStatus.CANCELLED, error="Cancelled by request")
        else:
            self._finish(job, JobStatus.COMPLETED)

    def _make_reporter(self, job: Job) -> ProgressReporter:
        def report(progress: float, message: Optional[str] = None) -> None:
            if job.is_cancelling:
                return
            job.progress = max(0.0, min(progress, 100.0))
            if message:
                job.message = message
                job.append_log(message)
            self._store.save(job)
            self._publish(ev.JOB_PROGRESS, job)

        return report

    def _finish(self, job: Job, status: JobStatus, error: Optional[str] = None, trace: Optional[str] = None) -> None:
        job.status = status
        if error:
            job.error = error
            job.append_log(error)
        if trace:
            job.append_log(trace)
        if status == JobStatus.COMPLETED:
            job.progress = 100.0
        job.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        self._store.save(job)
        with self._lock:
            self._running.pop(job.job_id, None)
        self._publish(ev.JOB_COMPLETED if status == JobStatus.COMPLETED else ev.JOB_FAILED, job)

    def _publish(self, event_type: str, job: Job) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish_async(
                SystemEvent(
                    type=event_type,
                    source="jobs.queue",
                    priority=EventPriority.NORMAL,
                    data={"job": job.to_dict()},
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to publish job event %s", event_type)
