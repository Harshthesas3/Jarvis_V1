"""Task scheduler for delayed and recurring execution."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Optional

from jarvis.types import ExecutionGraph

logger = logging.getLogger("jarvis.execution.scheduler")


class ScheduledTask:
    """A task scheduled for future execution."""

    def __init__(
        self,
        task_id: str,
        graph: ExecutionGraph,
        execute_fn: Callable[[ExecutionGraph], None],
        interval_seconds: Optional[float] = None,
        delay_seconds: float = 0,
    ) -> None:
        self.task_id = task_id
        self.graph = graph
        self._execute_fn = execute_fn
        self.interval_seconds = interval_seconds
        self.delay_seconds = delay_seconds
        self._cancel_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        def _run() -> None:
            if self.delay_seconds > 0 and self._cancel_event.wait(self.delay_seconds):
                return
            while True:
                self._execute_fn(self.graph)
                if self.interval_seconds is None or self._cancel_event.wait(self.interval_seconds):
                    break

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()


class TaskScheduler:
    """Manages scheduled and recurring task execution."""

    def __init__(self) -> None:
        self._tasks: Dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()

    def schedule_once(self, task_id: str, graph: ExecutionGraph, execute_fn: Callable[[ExecutionGraph], None], delay_seconds: float) -> ScheduledTask:
        task = ScheduledTask(task_id=task_id, graph=graph, execute_fn=execute_fn, delay_seconds=delay_seconds)
        with self._lock:
            self._tasks[task_id] = task
        task.start()
        return task

    def schedule_recurring(self, task_id: str, graph: ExecutionGraph, execute_fn: Callable[[ExecutionGraph], None], interval_seconds: float) -> ScheduledTask:
        task = ScheduledTask(task_id=task_id, graph=graph, execute_fn=execute_fn, interval_seconds=interval_seconds)
        with self._lock:
            self._tasks[task_id] = task
        task.start()
        return task

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task.cancel()
            del self._tasks[task_id]
            return True

    def cancel_all(self) -> None:
        with self._lock:
            for task in self._tasks.values():
                task.cancel()
            self._tasks.clear()

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._tasks)
