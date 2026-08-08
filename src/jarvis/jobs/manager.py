"""Facade for the background job system.

JobManager is the canonical public name; implementation is shared with JobService.
"""

from __future__ import annotations

from jarvis.jobs.service import JobService

JobManager = JobService

__all__ = ["JobManager"]
