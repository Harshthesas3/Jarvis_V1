"""JARVIS Application bootstrap — wires layers through DI container and event bus."""

from __future__ import annotations

import logging
import os
import queue as _queue
import time
from typing import Any, Dict, Optional, cast

# StartupManager is imported lazily inside initialize() to keep import time short.

from jarvis.di.container import ServiceContainer
from jarvis.eventbus.bus import InMemoryEventBus
from jarvis.eventbus.events import (
    SYSTEM_STARTED,
    SYSTEM_STARTING,
    SYSTEM_STOPPED,
    SYSTEM_STOPPING,
    WAKE_WORD_DETECTED,
    COMMAND_RECEIVED,
    PLANNING_STARTED,
    PLANNING_COMPLETE,
    ERROR_OCCURRED,
)
from jarvis.execution.engine import GraphExecutionEngine
from jarvis.execution.tracker import ExecutionTracker
from jarvis.execution.scheduler import TaskScheduler
from jarvis.interfaces.events import SystemEvent, EventPriority
from jarvis.types import ServiceHealth
from jarvis.telemetry import LatencyCollector
from jarvis.memory.project_state import ProjectStateMemory

logger = logging.getLogger("jarvis.app")

from jarvis.speech.playback import play_wav_async, stop_sound, wait_for_playback



class JarvisApplication:
    """Main application controller managing service lifecycle through DI and event bus."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._container = ServiceContainer()
        self._event_bus = InMemoryEventBus()
        self._engine: Optional[GraphExecutionEngine] = None
        self._tracker: Optional[ExecutionTracker] = None
        self._scheduler: Optional[TaskScheduler] = None
        self._job_service: Optional[Any] = None
        self._workspace_manager: Optional[Any] = None
        self._build_pipeline: Optional[Any] = None
        self._config_path = config_path
        self._running = False
        self._start_time: float = 0.0
        self._fast_router = None
        # Pre-warmed components populated by StartupManager during initialize()
        self._wake_model: Optional[Any] = None
        self._cmd_model: Optional[Any] = None
        self._speaker: Optional[Any] = None
        self._startup_manager: Optional[Any] = None
        self._register_core_services()

    def _register_core_services(self) -> None:
        from jarvis.services.config import ConfigService
        from jarvis.services.logging import LoggingService
        from jarvis.services.identity import IdentityManager
        from jarvis.services.response_engine import DynamicResponseEngine

        cfg = ConfigService(path=self._config_path)
        self._container.register_instance(ConfigService, cfg)
        self._container.register_instance(LoggingService, LoggingService())
        self._container.register_instance(IdentityManager, IdentityManager())
        self._container.register_instance(DynamicResponseEngine, DynamicResponseEngine())

    def initialize(self) -> None:
        self._start_time = time.time()
        self._event_bus.publish(SystemEvent(type=SYSTEM_STARTING, source="app"))
        self._logger = logging.getLogger("jarvis.app")
        self._logger.info("JARVIS v3.0.0 initializing...")

        self._engine = GraphExecutionEngine(event_bus=self._event_bus)
        self._tracker = ExecutionTracker()
        self._scheduler = TaskScheduler()

        self._container.register_instance(GraphExecutionEngine, self._engine)
        self._container.register_instance(InMemoryEventBus, self._event_bus)
        self._container.register_instance(ExecutionTracker, self._tracker)
        self._container.register_instance(TaskScheduler, self._scheduler)

        self._register_job_system()
        self._register_handlers()

        # Pre-warm all expensive subsystems concurrently before signalling ready.
        self._prewarm()

        self._event_bus.publish(SystemEvent(type=SYSTEM_STARTED, source="app"))
        self._logger.info("JARVIS initialization complete")

    def _register_job_system(self) -> None:
        from jarvis.jobs.queue import BackgroundJobQueue
        from jarvis.jobs.service import JobService
        from jarvis.jobs.store import JobStore
        from jarvis.workspace.manager import WorkspaceManager
        from jarvis.build.engine import BuildPipeline, register_build_handler
        from jarvis.opencode.session import register_default_handler as register_opencode_handler

        self._job_store = JobStore()
        self._job_queue = BackgroundJobQueue(self._job_store, event_bus=self._event_bus, workers=2)
        self._job_service = JobService(self._job_store, self._job_queue)
        self._workspace_manager = WorkspaceManager(event_bus=self._event_bus)
        self._build_pipeline = BuildPipeline(workspace_manager=self._workspace_manager, event_bus=self._event_bus)

        register_build_handler(self._job_service, pipeline=self._build_pipeline)
        register_opencode_handler(self._job_service, event_bus=self._event_bus, workspace_manager=self._workspace_manager)

        # Phase 11: project-state memory — bridges job store + workspace manager
        self._project_memory = ProjectStateMemory(
            job_service=self._job_service,
            workspace_manager=self._workspace_manager,
        )

        # Phase 12: latency telemetry singleton
        self._telemetry = LatencyCollector.instance()

        # Wire event subscribers
        from jarvis.eventbus.subscribers import TelemetrySubscriber, SystemLogSubscriber
        self._telemetry_sub = TelemetrySubscriber()
        self._syslog_sub = SystemLogSubscriber()
        self._event_bus.subscribe_all(self._telemetry_sub.handle_event)
        self._event_bus.register_subscriber(self._syslog_sub)

        self._container.register_instance(JobService, self._job_service)
        self._container.register_instance(WorkspaceManager, self._workspace_manager)
        self._container.register_instance(BuildPipeline, self._build_pipeline)
        self._container.register_instance(ProjectStateMemory, self._project_memory)
        self._container.register_instance(LatencyCollector, self._telemetry)
        self._logger.info("Job system registered: %s kinds", len(self._job_queue._handlers))

    def _register_handlers(self) -> None:
        if self._engine is None:
            return
        from jarvis.execution.adapter import ADAPTER_ACTIONS, LegacyHandlerAdapter
        for action_name, handler_fn in ADAPTER_ACTIONS.items():
            self._engine.register_handler(LegacyHandlerAdapter(action_name, handler_fn))

    def _prewarm(self) -> None:
        """Launch concurrent pre-warming of all expensive subsystems.

        Runs StartupManager.prewarm_all() which blocks until all tasks finish
        or timeout (30 s).  If prewarm succeeds the pre-loaded models are saved
        onto self so _main_loop() can use them immediately.
        """
        from jarvis.services.config import ConfigService
        from jarvis.startup import get_startup_manager
        from jarvis.startup.telemetry import StartupTelemetry

        cfg = self._container.resolve(ConfigService)
        mgr = get_startup_manager()
        self._startup_manager = mgr

        mgr.prewarm_all(cfg)

        # Retrieve pre-loaded components (None if that subsystem failed)
        if mgr.is_ready("whisper"):
            self._wake_model = mgr.wake_model
            self._cmd_model = mgr.cmd_model
        if mgr.is_ready("piper"):
            self._speaker = mgr.speaker
        if mgr.is_ready("router"):
            self._fast_router = mgr.fast_router

        # Record startup timing into telemetry
        st = StartupTelemetry()
        timeline = mgr.get_timeline()
        st.record_startup(timeline, warm=False)
        st.report(timeline)

    def run(self) -> None:
        if self._running:
            return
        self.initialize()
        self._running = True
        self._logger.info("JARVIS ready.")
        try:
            self._main_loop()
        except KeyboardInterrupt:
            self._logger.info("Interrupted")
        finally:
            self.shutdown()

    def _main_loop(self) -> None:
        from jarvis.services.config import ConfigService
        cfg = self._container.resolve(ConfigService)
        piper = cfg.get("paths.piper_exe")
        voice = cfg.get("paths.voice_model")
        import sounddevice as sd
        import numpy as np

        # Use pre-warmed models if available; lazy-load only as fallback.
        wake_model = self._wake_model
        cmd_model = self._cmd_model
        if wake_model is None or cmd_model is None:
            from faster_whisper import WhisperModel
            wake_model_size = cfg.get("models.stt_wake_model", "tiny")
            cmd_model_size = cfg.get("models.stt_command_model", "distil-whisper/distil-small.en")
            self._logger.info(
                "Pre-warm missed — loading ASR models now (cold): wake=%s cmd=%s",
                wake_model_size, cmd_model_size,
            )
            try:
                wake_model = WhisperModel(wake_model_size, device="cpu", compute_type="int8")
                cmd_model = WhisperModel(cmd_model_size, device="cpu", compute_type="int8")
            except Exception as exc:
                self._logger.warning(
                    "Could not load distil model (%s), falling back to 'base': %s",
                    cmd_model_size, exc,
                )
                wake_model = WhisperModel("base", device="cpu", compute_type="int8")
                cmd_model = WhisperModel("base", device="cpu", compute_type="int8")
        else:
            self._logger.info("ASR models ready (pre-warmed). No cold start.")

        from jarvis.execution.adapter import quick_plan, execute_via_engine
        from scipy.io.wavfile import write as write_wav
        fs = 16000
        phrases = cfg.get("voice.wake_phrases", ["i'm back"])

        tel = getattr(self, "_telemetry", None) or LatencyCollector.instance()
        proj_mem = getattr(self, "_project_memory", None)

        while self._running:
            try:
                self._logger.info("Sleeping... Say: %s", phrases[0])
                while self._running:
                    tel.start_turn()
                    tel.start_stage("wake")
                    rec = sd.rec(2 * fs, samplerate=fs, channels=1, dtype="int16")
                    sd.wait()
                    write_wav("wake.wav", fs, rec)
                    segs, _ = wake_model.transcribe("wake.wav", language="en")
                    tel.end_stage("wake")
                    text = " ".join(s.text for s in segs).lower().strip()
                    if text:
                        self._logger.info("Heard: %s", text)
                    if any(p in text for p in phrases):
                        self._event_bus.publish(SystemEvent(type=WAKE_WORD_DETECTED, source="app"))
                        self._tts(piper, voice, "Systems online, sir. Awaiting instructions.")
                        break

                while self._running:
                    tel.start_stage("recording")
                    user = self._capture_command(cmd_model)
                    tel.end_stage("recording")
                    if not user:
                        continue
                    self._event_bus.publish(SystemEvent(type=COMMAND_RECEIVED, source="app", data={"text": user}))

                    cleaned_user = user.lower().strip().rstrip(".").strip()
                    if cleaned_user in ["stop", "wait", "jarvis", "hold on", "actually", "pause"]:
                        self._logger.info("Interruption keyword '%s' detected. Halting and listening.", cleaned_user)
                        stop_sound()
                        try:
                            from jarvis.speech.piper_rt import get_speaker as _gs
                            _gs(voice).stop()
                        except Exception:
                            pass
                        self._tts(piper, voice, "Listening, sir.")
                        continue

                    if any(p in user.lower() for p in ("go to sleep", "goodbye", "bye jarvis")):
                        self._tts(piper, voice, "Goodbye sir.")
                        tel.finish_turn({"action": "sleep"})
                        break

                    # Phase 11: memory context injection
                    mem_ctx = proj_mem.build_context_block() if proj_mem else ""

                    self._event_bus.publish(SystemEvent(type=PLANNING_STARTED, source="app", data={"text": user}))
                    with tel.measure("intent"):
                        plan = quick_plan(user)
                    from jarvis.eventbus.events import IntentRecognized
                    self._event_bus.publish(SystemEvent(type=IntentRecognized, source="planner", data={"plan": plan}))

                    with tel.measure("llm"):
                        result = execute_via_engine(self._engine, plan, user) if plan else "I could not understand, sir."

                    # Deduplicate: skip identical back-to-back responses
                    if proj_mem and proj_mem.is_duplicate_response(result):
                        self._logger.info("Skipping duplicate response.")
                        tel.finish_turn({"action": plan.get("action") if plan else "unknown"})
                        continue

                    self._event_bus.publish(SystemEvent(type=PLANNING_COMPLETE, source="app", data={"result": result[:200]}))
                    if result and self._running:
                        with tel.measure("tts"):
                            self._tts(piper, voice, result)

                    tel.finish_turn({"action": plan.get("action") if plan else "unknown", "mem_ctx": bool(mem_ctx)})
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._event_bus.publish(SystemEvent(type=ERROR_OCCURRED, source="app", data={"error": str(exc)}))
                self._logger.exception("Main loop error")

    def _capture_command(self, model) -> str:
        from jarvis.speech.piper_rt import get_speaker
        from jarvis.services.config import ConfigService
        cfg = self._container.resolve(ConfigService)
        voice = cfg.get("paths.voice_model")

        import sounddevice as sd
        import numpy as np
        from scipy.io.wavfile import write as write_wav
        fs = 16000
        chunk_frames = int(fs * 0.1)
        chunks: list[np.ndarray] = []
        started = False
        silent_chunks = 0
        waited = 0
        max_wait = 30.0
        max_chunks = int(max_wait / 0.1)
        threshold = 0.02

        import queue as _queue
        q = _queue.Queue(maxsize=128)

        def _cb(indata, frames, time_info, status):
            vol = float(np.linalg.norm(indata) / np.sqrt(len(indata)))
            try:
                q.put_nowait((vol, indata.copy()))
            except _queue.Full:
                pass

        with sd.InputStream(samplerate=fs, channels=1, dtype="float32", callback=_cb, blocksize=chunk_frames):
            while True:
                try:
                    vol, data = q.get(timeout=0.1)
                except _queue.Empty:
                    continue
                
                waited += 1
                is_playing = False
                try:
                    sp = get_speaker(voice)
                    is_playing = sp._synth_in_flight() or not sp._audio_q.empty()
                except Exception:
                    pass

                current_threshold = threshold * 1.5 if is_playing else threshold

                if vol > current_threshold:
                    if is_playing:
                        self._logger.info("Interruption detected. Stopping playback.")
                        stop_sound()
                        try:
                            get_speaker(voice).stop()
                        except Exception:
                            pass
                        from jarvis.eventbus.events import PlaybackInterrupted
                        self._event_bus.publish(SystemEvent(type=PlaybackInterrupted, source="voice"))
                    if not started:
                        started = True
                    chunks.append(data)
                    silent_chunks = 0
                elif started:
                    chunks.append(data)
                    silent_chunks += 1
                    if silent_chunks >= 6:  # 0.6 s of trailing silence
                        break
                if not started and waited >= max_chunks:
                    break

        if not chunks:
            return ""
        
        # Save to wav format using numpy directly to avoid disk write if possible, but keep compatibility
        write_wav("command.wav", fs, (np.concatenate(chunks) * 32767).astype(np.int16))
        try:
            segs, _ = model.transcribe("command.wav", language="en")
        except Exception as exc:
            self._logger.warning("Command transcription failed: %s", exc)
            return ""
        return " ".join(s.text for s in segs).strip()

    def _tts(self, piper: str, voice: str, text: str) -> None:
        self._logger.info("JARVIS: %s", text)
        if not text:
            return
        clean = text.encode("ascii", errors="ignore").decode().strip()
        if not clean:
            return
        from jarvis.speech.piper_rt import get_speaker
        try:
            sp = get_speaker(voice)
            from jarvis.eventbus.events import SpeechStarted, SpeechFinished
            self._event_bus.publish(SystemEvent(type=SpeechStarted, source="voice", data={"text": clean}))
            sp.speak(clean, blocking=True)
            self._event_bus.publish(SystemEvent(type=SpeechFinished, source="voice", data={"text": clean}))
        except Exception as exc:
            self._logger.warning("In-process TTS failed, falling back to subprocess: %s", exc)
            # Fallback
            import subprocess
            wav_filename = f"response_{int(time.time() * 1000)}.wav"
            try:
                subprocess.run(
                    [piper, "-m", voice, "-f", wav_filename],
                    input=clean, text=True, capture_output=True, timeout=30,
                )
                play_wav_async(wav_filename)
                wait_for_playback()
            except Exception:
                self._logger.exception("Fallback TTS failed")

    def run_api_server(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        """Start JARVIS in API server mode using FastAPI + uvicorn."""
        from jarvis.api.server import run_server

        self.initialize()
        self._running = True
        try:
            run_server(self, host=host, port=port)
        except KeyboardInterrupt:
            self._logger.info("API server interrupted")
        finally:
            self.shutdown()

    # -- internal planning helper used by the API layer --

    def speak(self, text: str) -> None:
        """Synthesize speech via piper TTS (public, used by API layer)."""
        from jarvis.services.config import ConfigService
        cfg = self._container.resolve(ConfigService)
        piper = cfg.get("paths.piper_exe")
        voice = cfg.get("paths.voice_model")
        self._tts(piper, voice, text)

    def _plan(self, text: str) -> dict:
        """Plan a command, checking fast commands before the planner."""
        if self._fast_router is None:
            from jarvis.fast_command_router import get_fast_router
            self._fast_router = get_fast_router()
        fast = self._fast_router.route(text)
        if fast:
            return fast
        from jarvis.execution.adapter import quick_plan
        plan = quick_plan(text)
        return plan or {"action": "ai_chat", "text": text}

    def execute_plan(self, plan: dict) -> str:
        """Execute a plan dict using the execution engine (via adapter)."""
        if self._engine is None:
            return "Execution engine not available, sir."
        from jarvis.execution.adapter import execute_via_engine
        return execute_via_engine(self._engine, plan, "")

    def chat_with_llm(self, text: str, history: Optional[list] = None, speaker=None) -> str:
        from jarvis.services.config import ConfigService
        cfg = self._container.resolve(ConfigService)
        model = cfg.get("models.chat_model", "qwen3.5:4b")
        sp = cfg.get("system.system_prompt", "You are JARVIS.")

        # Phase 11: inject project-state memory block into system prompt
        proj_mem = getattr(self, "_project_memory", None)
        if proj_mem:
            ctx = proj_mem.build_context_block()
            if ctx:
                sp = sp + "\n\n" + ctx

        msgs = [{"role": "system", "content": sp}]
        if history:
            msgs.extend(history[-20:])
        msgs.append({"role": "user", "content": text})

        # Streaming path: feed tokens into TTS speaker sentence-by-sentence
        if speaker is not None:
            try:
                from jarvis.speech.streaming_llm import stream_response_to_speaker
                return stream_response_to_speaker(text, model, msgs, speaker)
            except Exception as exc:
                self._logger.warning("LLM streaming failed, falling back to sync: %s", exc)

        # Non-streaming fallback (headless / API mode)
        try:
            from jarvis.planner.llm import _get_client
            return _get_client().chat(model=model, messages=msgs, think=False, keep_alive=-1).get(
                "message", {}
            ).get("content", "")
        except Exception as exc:
            self._logger.warning("LLM chat failed: %s", exc)
            return "I am having trouble reaching the language model, sir."

    def shutdown(self) -> None:
        self._event_bus.publish(SystemEvent(type=SYSTEM_STOPPING, source="app"))
        self._running = False
        if self._scheduler:
            self._scheduler.cancel_all()
        if self._job_service:
            try:
                self._job_service.shutdown()
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("Job service shutdown error: %s", exc)
        self._container.shutdown()
        self._event_bus.publish(SystemEvent(type=SYSTEM_STOPPED, source="app"))
        self._logger.info("JARVIS shutdown complete")

    def build_project(self, name: str, description: str = "", instruction: str = "") -> Any:
        """Submit a background project build (workspace + spec + OpenCode).

        Returns immediately with a Job; the build runs on the job queue.
        """
        if self._job_service is None:
            raise RuntimeError("Job system not initialized")
        return self._job_service.submit(
            "build_project",
            {"name": name, "description": description, "instruction": instruction},
        )

    def health_check(self) -> Dict[str, ServiceHealth]:
        health = {
            "event_bus": ServiceHealth(name="event_bus", healthy=True),
            "engine": ServiceHealth(name="engine", healthy=self._engine is not None),
            "job_service": ServiceHealth(name="job_service", healthy=self._job_service is not None),
        }
        # Include per-subsystem startup readiness if pre-warm has run
        if self._startup_manager is not None:
            for subsystem in ("whisper", "ollama", "piper", "chroma", "router"):
                ready = self._startup_manager.is_ready(subsystem)
                health[f"startup_{subsystem}"] = ServiceHealth(name=f"startup_{subsystem}", healthy=ready)
        return health

    @property
    def container(self) -> ServiceContainer:
        return self._container

    @property
    def event_bus(self) -> InMemoryEventBus:
        return self._event_bus

    @property
    def engine(self) -> Optional[GraphExecutionEngine]:
        return self._engine