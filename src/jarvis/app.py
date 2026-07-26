"""JARVIS Application bootstrap — wires layers through DI container and event bus."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

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
        self._config_path = config_path
        self._running = False
        self._start_time: float = 0.0
        self._fast_router = None
        self._register_core_services()

    def _register_core_services(self) -> None:
        from jarvis.services.config import ConfigService
        from jarvis.services.logging import LoggingService

        cfg = ConfigService(path=self._config_path)
        self._container.register_instance(ConfigService, cfg)
        self._container.register_instance(LoggingService, LoggingService())

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

        self._register_handlers()
        self._event_bus.publish(SystemEvent(type=SYSTEM_STARTED, source="app"))
        self._logger.info("JARVIS initialization complete")

    def _register_handlers(self) -> None:
        if self._engine is None:
            return
        from jarvis.execution.adapter import ADAPTER_ACTIONS, LegacyHandlerAdapter
        for action_name, handler_fn in ADAPTER_ACTIONS.items():
            self._engine.register_handler(LegacyHandlerAdapter(action_name, handler_fn))

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
        from faster_whisper import WhisperModel

        self._logger.info("Loading ASR models...")
        wake_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        cmd_model = WhisperModel("base", device="cpu", compute_type="int8")
        self._logger.info("Models loaded.")

        from jarvis.execution.adapter import quick_plan, execute_via_engine
        from scipy.io.wavfile import write as write_wav
        fs = 16000
        phrases = cfg.get("voice.wake_phrases", ["i'm back"])

        while self._running:
            try:
                self._logger.info("Sleeping... Say: %s", phrases[0])
                while self._running:
                    rec = sd.rec(int(2 * fs), samplerate=fs, channels=1, dtype="int16")
                    sd.wait()
                    write_wav("wake.wav", fs, rec)
                    segs, _ = wake_model.transcribe("wake.wav", language="en")
                    text = " ".join(s.text for s in segs).lower().strip()
                    if text:
                        self._logger.info("Heard: %s", text)
                    if any(p in text for p in phrases):
                        self._event_bus.publish(SystemEvent(type=WAKE_WORD_DETECTED, source="app"))
                        self._tts(piper, voice, "Systems online, sir. Awaiting instructions.")
                        break

                while self._running:
                    user = self._capture_command(cmd_model)
                    if not user:
                        continue
                    self._event_bus.publish(SystemEvent(type=COMMAND_RECEIVED, source="app", data={"text": user}))
                    if any(p in user.lower() for p in ("go to sleep", "goodbye", "bye jarvis")):
                        self._tts(piper, voice, "Goodbye sir.")
                        break
                    self._event_bus.publish(SystemEvent(type=PLANNING_STARTED, source="app", data={"text": user}))
                    plan = quick_plan(user)
                    result = execute_via_engine(self._engine, plan, user) if plan else "I could not understand, sir."
                    self._event_bus.publish(SystemEvent(type=PLANNING_COMPLETE, source="app", data={"result": result[:200]}))
                    if result and self._running:
                        self._tts(piper, voice, result)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._event_bus.publish(SystemEvent(type=ERROR_OCCURRED, source="app", data={"error": str(exc)}))
                self._logger.exception("Main loop error")

    def _capture_command(self, model) -> str:
        # Interrupt currently playing sound when capturing new command
        stop_sound()
        import sounddevice as sd
        import numpy as np
        from scipy.io.wavfile import write as write_wav
        fs = 16000
        chunk = int(fs * 0.2)
        chunks = []
        silent = 0
        started = False
        max_wait = 30
        waited = 0

        def cb(indata, frames, time_info, status):
            nonlocal silent, started, waited
            vol = np.linalg.norm(indata) / np.sqrt(len(indata))
            if vol > 0.02:
                if not started:
                    started = True
                silent = 0
                waited = 0
                chunks.append(indata.copy())
            elif started:
                silent += 1
                waited += 1
                chunks.append(indata.copy())

        with sd.InputStream(samplerate=fs, channels=1, dtype="float32", callback=cb, blocksize=chunk):
            while not started or silent < int(1.5 / 0.2):
                sd.sleep(100)
                waited += 1
                if waited > max_wait * 10:
                    break

        if not chunks:
            return ""
        write_wav("command.wav", fs, (np.concatenate(chunks) * 32767).astype(np.int16))
        try:
            segs, _ = model.transcribe("command.wav", language="en")
        except Exception as exc:
            self._logger.warning("Command transcription failed: %s", exc)
            return ""
        return " ".join(s.text for s in segs).strip()

    def _tts(self, piper: str, voice: str, text: str) -> None:
        import subprocess
        self._logger.info("JARVIS: %s", text)
        if not piper or not voice or not text:
            return
        clean = text.encode("ascii", errors="ignore").decode().strip()
        if not clean:
            return
        
        # Use unique filename
        wav_filename = f"response_{int(time.time() * 1000)}.wav"
        try:
            r = subprocess.run(
                [piper, "-m", voice, "-f", wav_filename],
                input=clean, text=True, capture_output=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            self._logger.warning("TTS timed out")
            return
        except Exception as exc:
            self._logger.warning("TTS subprocess failed: %s", exc)
            return
        if r.returncode != 0:
            self._logger.warning("TTS error: %s", r.stderr.decode(errors="ignore"))
            return

        # Play and block until audio finishes — prevents TTS cutoff
        play_wav_async(wav_filename)
        wait_for_playback()

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

    def chat_with_llm(self, text: str, history: Optional[list] = None) -> str:
        import ollama
        from jarvis.services.config import ConfigService
        cfg = self._container.resolve(ConfigService)
        model = cfg.get("models.chat_model", "qwen3.5:4b")
        sp = cfg.get("system.system_prompt", "You are JARVIS.")
        msgs = [{"role": "system", "content": sp}]
        if history:
            msgs.extend(history[-20:])
        msgs.append({"role": "user", "content": text})
        try:
            from jarvis.planner.llm import _get_client
            return _get_client().chat(model=model, messages=msgs)["message"]["content"]
        except Exception as exc:
            self._logger.warning("LLM chat failed: %s", exc)
            return "I am having trouble reaching the language model, sir."

    def shutdown(self) -> None:
        self._event_bus.publish(SystemEvent(type=SYSTEM_STOPPING, source="app"))
        self._running = False
        if self._scheduler:
            self._scheduler.cancel_all()
        self._container.shutdown()
        self._event_bus.publish(SystemEvent(type=SYSTEM_STOPPED, source="app"))
        self._logger.info("JARVIS shutdown complete")

    def health_check(self) -> Dict[str, ServiceHealth]:
        return {
            "event_bus": ServiceHealth(name="event_bus", healthy=True),
            "engine": ServiceHealth(name="engine", healthy=self._engine is not None),
        }

    @property
    def container(self) -> ServiceContainer:
        return self._container

    @property
    def event_bus(self) -> InMemoryEventBus:
        return self._event_bus

    @property
    def engine(self) -> Optional[GraphExecutionEngine]:
        return self._engine