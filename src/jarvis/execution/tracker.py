"""Execution tracking and metrics collection."""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from jarvis.types import ExecutionResult, PlanStatus, TaskResult, TaskStatus


class ExecutionTracker:
    """Tracks execution history with timing and success/failure stats.

    Thread-safe sliding window of recent executions.
    """

    def __init__(self, max_history: int = 100) -> None:
        self._lock = threading.Lock()
        self._max_history = max_history
        self._history: List[ExecutionResult] = []
        self._action_stats: Dict[str, dict] = {}

    def record(self, result: ExecutionResult) -> None:
        with self._lock:
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            for task_id, task_result in result.task_results.items():
                action = task_id.split("_")[0] if "_" in task_id else "unknown"
                if action not in self._action_stats:
                    self._action_stats[action] = {"calls": 0, "failures": 0, "total_duration_ms": 0.0}
                self._action_stats[action]["calls"] += 1
                self._action_stats[action]["total_duration_ms"] += task_result.duration_ms
                if task_result.status == TaskStatus.FAILED:
                    self._action_stats[action]["failures"] += 1

    def get_history(self, limit: Optional[int] = None) -> List[ExecutionResult]:
        with self._lock:
            results = list(self._history)
            return results[-limit:] if limit else results

    def get_recent_failures(self, limit: int = 10) -> List[TaskResult]:
        failures: List[TaskResult] = []
        with self._lock:
            for result in reversed(self._history):
                for tr in result.task_results.values():
                    if tr.status == TaskStatus.FAILED and len(failures) < limit:
                        failures.append(tr)
        return failures

    def get_action_stats(self) -> Dict[str, dict]:
        with self._lock:
            stats = {}
            for action, data in self._action_stats.items():
                calls = data["calls"]
                stats[action] = {
                    "calls": calls,
                    "failures": data["failures"],
                    "success_rate": round((calls - data["failures"]) / calls * 100, 1) if calls > 0 else 100.0,
                    "avg_duration_ms": round(data["total_duration_ms"] / calls, 1) if calls > 0 else 0,
                }
            return stats

    def get_summary(self) -> dict:
        with self._lock:
            total = len(self._history)
            completed = sum(1 for r in self._history if r.status == PlanStatus.COMPLETED)
            failed = sum(1 for r in self._history if r.status in (PlanStatus.FAILED, PlanStatus.PARTIALLY_COMPLETED))
            cancelled = sum(1 for r in self._history if r.status == PlanStatus.CANCELLED)
            total_duration = sum(r.total_duration_ms for r in self._history)
            return {
                "total_executions": total,
                "completed": completed,
                "failed": failed,
                "cancelled": cancelled,
                "total_duration_ms": round(total_duration, 1),
                "avg_duration_ms": round(total_duration / total, 1) if total > 0 else 0,
            }
