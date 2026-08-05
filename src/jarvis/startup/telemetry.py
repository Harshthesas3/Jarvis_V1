"""Startup telemetry — integrates pre-warm timing with the LatencyCollector.

Records a structured ``startup`` entry in ``data/latency_benchmarks.json``
so cold vs warm startup times can be compared over time.

Usage
-----
::

    from jarvis.startup.telemetry import StartupTelemetry

    st = StartupTelemetry()
    st.record_startup(manager.get_timeline(), warm=False)
    st.report()
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("jarvis.startup.telemetry")

_DEFAULT_PATH = os.path.join(os.getcwd(), "data", "latency_benchmarks.json")


class StartupTelemetry:
    """Records and reports startup timing data.

    Parameters
    ----------
    output_path : str, optional
        Path to the JSONL benchmark file.
        Defaults to ``data/latency_benchmarks.json``.
    """

    def __init__(self, output_path: str | None = None) -> None:
        self._path = output_path or os.environ.get("JARVIS_BENCH_PATH", _DEFAULT_PATH)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def record_startup(
        self,
        timeline: Dict[str, float],
        *,
        warm: bool = False,
    ) -> Dict[str, Any]:
        """Persist a startup timing record.

        Parameters
        ----------
        timeline : dict
            Subsystem name → elapsed ms mapping from ``StartupManager.get_timeline()``.
        warm : bool
            ``True`` if this is a warm start (models already cached on disk).

        Returns
        -------
        dict
            The record that was written.
        """
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "startup",
            "warm": warm,
        }
        for key, ms in timeline.items():
            record[f"startup_{key}_ms"] = round(ms, 1)

        try:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.debug("Startup record written: total=%.0f ms", timeline.get("__total__", 0))
        except OSError as exc:
            logger.warning("Could not write startup benchmark: %s", exc)

        return record

    def report(self, timeline: Dict[str, float]) -> None:
        """Print a human-readable startup timeline at INFO level."""
        total = timeline.get("__total__", 0.0)
        lines = [
            "Startup pre-warm summary",
            f"  {'Subsystem':<14} {'Time':>8}",
            f"  {'─' * 24}",
        ]
        ordered = [k for k in timeline if k != "__total__"]
        for name in ordered:
            ms = timeline[name]
            lines.append(f"  {name:<14} {ms:>7.0f} ms")
        lines.append(f"  {'─' * 24}")
        lines.append(f"  {'TOTAL (wall-clock)':<14} {total:>7.0f} ms")
        for line in lines:
            logger.info(line)

    def read_startup_records(self, limit: int = 20) -> list:
        """Return the most recent startup records from the benchmark file."""
        records = []
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("type") == "startup":
                            records.append(rec)
                    except json.JSONDecodeError:
                        pass
        except FileNotFoundError:
            pass
        return records[-limit:]

    def compare_cold_vs_warm(self) -> Dict[str, Any]:
        """Return min/mean/max total_ms split by cold and warm starts."""
        records = self.read_startup_records(limit=100)
        cold = [r.get("startup___total___ms", 0) for r in records if not r.get("warm")]
        warm = [r.get("startup___total___ms", 0) for r in records if r.get("warm")]

        def stats(vals):
            if not vals:
                return None
            return {
                "min_ms": round(min(vals), 1),
                "mean_ms": round(sum(vals) / len(vals), 1),
                "max_ms": round(max(vals), 1),
                "samples": len(vals),
            }

        return {"cold": stats(cold), "warm": stats(warm)}
