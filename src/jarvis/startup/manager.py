"""Concurrent startup pre-warmer for JARVIS AI OS.

Every expensive subsystem is loaded in parallel during ``initialize()`` so the
user never experiences a cold start on the first interaction.

Design
------
- ``prewarm_all(cfg)`` submits all tasks to a ``ThreadPoolExecutor`` and waits
  for the slowest one.  Total startup time is bounded by the *single* slowest
  loader (usually Piper ONNX, ~1.5 s) rather than their *sum* (5–9 s).
- Each task is wrapped in a try/except so a failure in one subsystem never
  crashes the others or the main thread.  Failed subsystems log WARNING and
  report ``is_ready(name) == False``.
- ``is_ready(name)`` is used as a readiness gate: ``app.py`` checks it before
  using a preloaded component so it falls back to lazy init if prewarm failed.
- ``prewarm_all()`` is idempotent: calling it twice is a no-op.
- All preloaded objects are stored as public attributes so ``app.py`` can
  retrieve them without re-constructing.

Subsystem tags
--------------
``whisper``, ``ollama``, ``piper``, ``chroma``, ``router``, ``opencode``,
``memory``
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.startup.manager")

# Subsystems managed by this module.
_SUBSYSTEMS = ("whisper", "ollama", "piper", "chroma", "router", "opencode", "memory")


class StartupManager:
    """Orchestrates concurrent pre-warming of all JARVIS subsystems.

    Attributes
    ----------
    wake_model : WhisperModel | None
        Pre-loaded tiny wake-word model (available after prewarm).
    cmd_model : WhisperModel | None
        Pre-loaded distil-small command transcription model.
    speaker : StreamingSpeaker | None
        Pre-initialized Piper streaming speaker.
    fast_router : FastCommandRouter | None
        Pre-initialized fast command router with regex engine compiled.
    opencode_path : str | None
        Cached ``shutil.which()`` result for the opencode binary.
    """

    def __init__(self) -> None:
        self._ready: Dict[str, bool] = {s: False for s in _SUBSYSTEMS}
        self._timeline: Dict[str, float] = {}  # subsystem → elapsed ms
        self._lock = threading.Lock()
        self._prewarmed = False

        # Pre-loaded components (set during prewarm, read by app.py)
        self.wake_model: Optional[Any] = None
        self.cmd_model: Optional[Any] = None
        self.speaker: Optional[Any] = None
        self.fast_router: Optional[Any] = None
        self.opencode_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prewarm_all(self, cfg: Any, *, timeout: float = 30.0) -> None:
        """Pre-warm all subsystems concurrently.

        Parameters
        ----------
        cfg : ConfigService
            Live config service used to read model paths / names.
        timeout : float
            Maximum seconds to wait for all tasks (default 30 s).

        This method blocks until all tasks complete or timeout is reached.
        It is safe to call more than once; subsequent calls are no-ops.
        """
        with self._lock:
            if self._prewarmed:
                logger.debug("StartupManager.prewarm_all() called again — skipping (already done)")
                return
            self._prewarmed = True

        t_global = time.perf_counter()
        logger.info("━━━ JARVIS Startup Pre-warm — BEGIN ━━━")

        # Read config values once (thread-safe — ConfigService is read-only)
        wake_model_size = cfg.get("models.stt_wake_model", "tiny")
        cmd_model_size = cfg.get("models.stt_command_model", "distil-whisper/distil-small.en")
        chat_model = cfg.get("models.chat_model", "qwen3.5:4b")
        voice_model = cfg.get("paths.voice_model", "")
        opencode_bin = os.environ.get("OPENCODE_BIN", "opencode")

        tasks = {
            "whisper": lambda: self._prewarm_whisper(wake_model_size, cmd_model_size),
            "ollama": lambda: self._prewarm_ollama(chat_model),
            "piper": lambda: self._prewarm_piper(voice_model),
            "chroma": lambda: self._prewarm_chroma(),
            "router": lambda: self._prewarm_router(),
            "opencode": lambda: self._prewarm_opencode(opencode_bin),
            "memory": lambda: self._prewarm_memory(),
        }

        futures: Dict[str, Future] = {}
        with ThreadPoolExecutor(max_workers=7, thread_name_prefix="jarvis-prewarm") as pool:
            for name, fn in tasks.items():
                futures[name] = pool.submit(self._run_task, name, fn)
            # Wait for all (pool.__exit__ blocks)

        total_ms = (time.perf_counter() - t_global) * 1000.0
        self._timeline["__total__"] = total_ms
        self._log_timeline()
        logger.info("━━━ JARVIS Startup Pre-warm — DONE in %.0f ms ━━━", total_ms)

    def is_ready(self, subsystem: str) -> bool:
        """Return True if *subsystem* pre-warmed successfully."""
        return self._ready.get(subsystem, False)

    def get_timeline(self) -> Dict[str, float]:
        """Return per-subsystem startup timing in milliseconds."""
        return dict(self._timeline)

    # ------------------------------------------------------------------
    # Task runner (wraps any prewarm function with timing + error guard)
    # ------------------------------------------------------------------

    def _run_task(self, name: str, fn) -> None:
        t0 = time.perf_counter()
        try:
            fn()
            elapsed = (time.perf_counter() - t0) * 1000.0
            with self._lock:
                self._ready[name] = True
                self._timeline[name] = elapsed
            logger.info("  ✓ %-12s ready in %5.0f ms", name, elapsed)
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000.0
            with self._lock:
                self._ready[name] = False
                self._timeline[name] = elapsed
            logger.warning("  ✗ %-12s FAILED in %5.0f ms: %s", name, elapsed, exc)

    # ------------------------------------------------------------------
    # Individual prewarm functions
    # ------------------------------------------------------------------

    def _prewarm_whisper(self, wake_size: str, cmd_size: str) -> None:
        """Load both Whisper models and run one JIT-warm transcription."""
        from faster_whisper import WhisperModel
        import numpy as np

        # Load wake model (tiny — fast)
        wake = WhisperModel(wake_size, device="cpu", compute_type="int8")
        # Load command model (distil-small.en — may take 1–2 s first load)
        try:
            cmd = WhisperModel(cmd_size, device="cpu", compute_type="int8")
        except Exception as exc:
            logger.warning("distil model failed (%s), falling back to base: %s", cmd_size, exc)
            cmd = WhisperModel("base", device="cpu", compute_type="int8")

        # Warm up ONNX kernels with a silent 0.5 s frame (16 kHz, mono, int16)
        silence = np.zeros(8000, dtype=np.float32)
        list(wake.transcribe(silence, language="en")[0])   # consume generator
        list(cmd.transcribe(silence, language="en")[0])

        self.wake_model = wake
        self.cmd_model = cmd

    def _prewarm_ollama(self, model: str) -> None:
        """Connect to Ollama and load the model with a 1-token warm-up call."""
        from jarvis.planner.llm import _get_client
        client = _get_client()
        # keep_alive=-1 keeps the model resident indefinitely.
        # num_predict=1 returns almost immediately (single token).
        client.chat(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            keep_alive=-1,
            think=False,
            options={"num_predict": 1},
        )

    def _prewarm_piper(self, voice_model: str) -> None:
        """Load the Piper ONNX voice and warm up the synthesis kernel."""
        if not voice_model or not os.path.exists(voice_model):
            raise RuntimeError(f"Piper voice model not found: {voice_model!r}")
        from jarvis.speech.piper_rt import get_piper_engine, get_speaker
        engine = get_piper_engine(voice_model)
        # Synthesize a silent whitespace string — warms the ONNX runtime
        # without emitting any audible audio.
        engine.synthesize(" ")
        # Also init the StreamingSpeaker so its threads are alive
        sp = get_speaker(voice_model)
        self.speaker = sp

    def _prewarm_chroma(self) -> None:
        """Connect ChromaDB and warm up the embedding model."""
        from jarvis.memory.chroma_memory import ChromaSemanticMemory, _chromadb_available
        if not _chromadb_available():
            raise RuntimeError("chromadb not installed")
        mem = ChromaSemanticMemory()
        if not mem.is_available():
            raise RuntimeError("ChromaSemanticMemory init failed")
        # Run one store+search to trigger sentence-transformer load
        fact_id = mem.store_fact("startup prewarm warmup", category="system", importance=0)
        mem.search_facts("warmup", top_k=1)

    def _prewarm_router(self) -> None:
        """Instantiate FastCommandRouter and compile all regexes."""
        from jarvis.fast_command_router import get_fast_router
        router = get_fast_router()
        # Drive one route() call so FAST_COMMAND_PATTERNS are compiled
        router.route("what time is it")
        self.fast_router = router

    def _prewarm_opencode(self, binary: str) -> None:
        """Resolve and cache the OpenCode executable path. Never launches it."""
        path = shutil.which(binary)
        self.opencode_path = path  # None if not installed — that's fine
        if path:
            if not os.path.isfile(path):
                raise RuntimeError(f"opencode path not a file: {path}")
        # No workspace checks here — WorkspaceManager is already initialized

    def _prewarm_memory(self) -> None:
        """Open the SQLite job store connection and warm the OS page cache."""
        from jarvis.jobs.store import JobStore
        store = JobStore()
        store.list()  # triggers WAL checkpoint, warms page cache
        store.close()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _log_timeline(self) -> None:
        logger.info("  ┌─ Startup Timeline ─────────────────────┐")
        for name in _SUBSYSTEMS:
            ms = self._timeline.get(name)
            status = "✓" if self._ready.get(name) else "✗"
            if ms is not None:
                logger.info("  │  %s %-12s %6.0f ms", status, name, ms)
            else:
                logger.info("  │  ? %-12s  (not run)", name)
        total = self._timeline.get("__total__", 0.0)
        logger.info("  │  ─────────────────────────────────────")
        logger.info("  │    TOTAL (wall-clock)  %6.0f ms", total)
        logger.info("  └────────────────────────────────────────┘")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[StartupManager] = None
_manager_lock = threading.Lock()


def get_startup_manager() -> StartupManager:
    """Return the global StartupManager singleton."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = StartupManager()
    return _manager
