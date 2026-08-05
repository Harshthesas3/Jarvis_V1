"""Structured latency telemetry for JARVIS.

Measures per-stage timing (wake → STT → intent → LLM → TTS → playback)
and writes structured JSON benchmarks to ``data/latency_benchmarks.json``.

Usage
-----
::

    from jarvis.telemetry.collector import LatencyCollector

    col = LatencyCollector.instance()
    with col.measure("stt"):
        text = model.transcribe(wav)

At the end of each turn ``col.finish_turn()`` flushes a record.

Records are appended to ``data/latency_benchmarks.json`` (newline-delimited
JSON, one record per turn) so the file can be analysed with any tool that
handles JSONL.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.telemetry.collector")

# Ordered pipeline stages.  "total" is computed automatically.
STAGES = ["wake", "recording", "stt", "intent", "memory", "llm", "tts", "playback"]

_DEFAULT_PATH = os.path.join(os.getcwd(), "data", "latency_benchmarks.json")


class LatencyCollector:
    """Per-turn latency recorder with JSONL persistence.

    Thread-safe; a single global instance is shared across all threads
    via :meth:`instance`.
    """

    _instance: Optional["LatencyCollector"] = None
    _instance_lock = threading.Lock()

    def __init__(self, output_path: Optional[str] = None) -> None:
        self._path = output_path or os.environ.get("JARVIS_BENCH_PATH", _DEFAULT_PATH)
        self._lock = threading.RLock()
        self._current: Dict[str, float] = {}  # stage → elapsed seconds
        self._turn_start: float = 0.0
        self._stage_starts: Dict[str, float] = {}
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    # ------------------------------------------------------------------
    # Global singleton
    # ------------------------------------------------------------------

    @classmethod
    def instance(cls) -> "LatencyCollector":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Turn lifecycle
    # ------------------------------------------------------------------

    def start_turn(self) -> None:
        """Mark the beginning of a new interaction turn."""
        with self._lock:
            self._turn_start = time.perf_counter()
            self._current = {}
            self._stage_starts = {}

    def finish_turn(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Compute total latency, persist the record, and return it."""
        with self._lock:
            total = time.perf_counter() - self._turn_start if self._turn_start else 0.0
            record: Dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_ms": round(total * 1000, 1),
            }
            for stage in STAGES:
                elapsed = self._current.get(stage)
                if elapsed is not None:
                    record[f"{stage}_ms"] = round(elapsed * 1000, 1)
            if extra:
                record.update(extra)
            self._append(record)
            self._current = {}
            self._stage_starts = {}
            return record

    # ------------------------------------------------------------------
    # Stage measurement
    # ------------------------------------------------------------------

    def record(self, stage: str, elapsed_seconds: float) -> None:
        """Record a pre-measured duration for *stage*."""
        with self._lock:
            self._current[stage] = elapsed_seconds

    @contextlib.contextmanager
    def measure(self, stage: str):
        """Context manager that records the wall-clock time of a block.

        ::

            with collector.measure("stt"):
                result = model.transcribe(wav)
        """
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.record(stage, time.perf_counter() - t0)

    def start_stage(self, stage: str) -> None:
        """Start timing *stage* manually (pair with :meth:`end_stage`)."""
        with self._lock:
            self._stage_starts[stage] = time.perf_counter()

    def end_stage(self, stage: str) -> None:
        """Stop timing *stage* and record it."""
        with self._lock:
            t0 = self._stage_starts.pop(stage, None)
            if t0 is not None:
                self._current[stage] = time.perf_counter() - t0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _append(self, record: Dict[str, Any]) -> None:
        """Append *record* as a newline-delimited JSON line."""
        try:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.debug("Benchmark written: total=%.0f ms", record.get("total_ms", 0))
        except OSError as exc:
            logger.warning("Could not write benchmark: %s", exc)

    def read_all(self, limit: int = 100) -> list:
        """Return up to *limit* most-recent benchmark records."""
        records = []
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except FileNotFoundError:
            pass
        return records[-limit:]

    def summarize(self) -> Dict[str, Any]:
        """Return min/mean/max for each stage across all stored records."""
        records = self.read_all(limit=500)
        if not records:
            return {}
        sums: Dict[str, list] = {}
        for rec in records:
            for key, val in rec.items():
                if key.endswith("_ms") and isinstance(val, (int, float)):
                    sums.setdefault(key, []).append(val)
        summary = {}
        for key, vals in sums.items():
            summary[key] = {
                "min_ms": round(min(vals), 1),
                "mean_ms": round(sum(vals) / len(vals), 1),
                "max_ms": round(max(vals), 1),
                "samples": len(vals),
            }
        return summary
