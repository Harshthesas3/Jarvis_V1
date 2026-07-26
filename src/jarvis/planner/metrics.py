"""Planner metrics for observability — tracks fast-path, LLM, and validation stats."""

from __future__ import annotations

import threading


class PlannerMetrics:
    """Lightweight thread-safe metrics for planner observability."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.fast_path_hits: int = 0
        self.fast_path_misses: int = 0
        self.llm_calls: int = 0
        self.llm_failures: int = 0
        self.llm_retries: int = 0
        self.multi_step_plans: int = 0
        self.validation_failures: int = 0
        self.circuit_breaker_hits: int = 0
        self.clarifications: int = 0
        self._total_duration_ms: float = 0.0

    def record_llm_call(self, duration_ms: float) -> None:
        with self._lock:
            self.llm_calls += 1
            self._total_duration_ms += duration_ms

    def record(self, **kwargs: int) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, getattr(self, k) + v)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "fast_path_hits": self.fast_path_hits,
                "fast_path_misses": self.fast_path_misses,
                "llm_calls": self.llm_calls,
                "llm_failures": self.llm_failures,
                "llm_retries": self.llm_retries,
                "multi_step_plans": self.multi_step_plans,
                "validation_failures": self.validation_failures,
                "circuit_breaker_hits": self.circuit_breaker_hits,
                "clarifications": self.clarifications,
                "total_duration_ms": round(self._total_duration_ms, 1),
            }


_METRICS = PlannerMetrics()


def get_metrics() -> PlannerMetrics:
    return _METRICS


def get_metrics_snapshot() -> dict:
    return _METRICS.snapshot()


def record_metric(**kwargs: int) -> None:
    _METRICS.record(**kwargs)