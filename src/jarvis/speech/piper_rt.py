"""Low-latency, in-process Piper TTS with streamed gapless playback.

Why this module exists
----------------------
The legacy `jarvis.speech.tts.TtsEngine` shells out to the `piper` CLI once
per utterance (~2.7 s of subprocess spawn + model load each time) and blocks
playback. For a voice assistant that must start speaking in <700 ms this is
the single biggest latency source.

This module loads the Piper ONNX voice ONCE, synthesizes in-process, and
plays synthesized audio through a persistent playout loop. Sentences can be
fed incrementally so playback overlaps with LLM generation.

Design
------
- ``PiperEngine`` holds the loaded voice and a synthesis lock (onnxruntime is
  not thread-safe for concurrent synthesis on one session).
- ``StreamingSpeaker`` runs a single playback worker that drains a queue of
  float32 samples and plays each chunk with ``sounddevice``. Feeding text
  while audio is already playing produces gapless output because the worker
  never stops the device between chunks.
- Text is split into sentences so short chunks start speaking quickly.

No new dependencies; uses ``piper-tts``, ``numpy``, ``sounddevice`` which are
already installed.
"""

from __future__ import annotations

import io
import logging
import queue
import re
import threading
import time
import wave
from typing import Optional

import numpy as np

logger = logging.getLogger("jarvis.speech.piper_rt")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\s+(?=[.!?])")

# Silence threshold below which a synthesized chunk is pure silence
_NOISE_FLOOR = 1.0 / 32768.0 * 2.0


def _split_sentences(text: str):
    """Split text into speakable fragments (sentences/clauses).

    Splits on sentence boundaries so we can start speaking the first clause
    almost immediately instead of waiting for the full response.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = _SENTENCE_SPLIT_RE.split(cleaned)
    out = []
    buf = ""
    for p in parts:
        buf += p
        if buf.endswith((".", "!", "?", ":", ";")) or len(buf) >= 26:
            if buf:
                out.append(buf.strip())
            buf = ""
    if buf:
        out.append(buf.strip())
    return [s for s in out if s]


def _has_audio(samples: np.ndarray) -> bool:
    if len(samples) == 0:
        return False
    return bool(np.max(np.abs(samples)) > _NOISE_FLOOR)


class PiperEngine:
    """In-process Piper voice wrapper. Loads the ONNX model exactly once."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._voice = None
        self._lock = threading.Lock()
        self.sample_rate = 22050
        self._load()

    def _load(self) -> None:
        from piper import PiperVoice

        t0 = time.perf_counter()
        self._voice = PiperVoice.load(self.model_path)
        logger.info("Piper voice loaded in %.0f ms", (time.perf_counter() - t0) * 1000.0)

    def synthesize(self, text: str) -> Optional[np.ndarray]:
        """Synthesize *text* and return float32 mono samples (or None)."""
        text = text.strip()
        if not text:
            return None
        with self._lock:
            if self._voice is None:
                return None
            try:
                wav_buf = io.BytesIO()
                with wave.open(wav_buf, "wb") as wf:
                    self._voice.synthesize_wav(text, wf)
                wav_buf.seek(0)
                with wave.open(wav_buf, "rb") as wf:
                    self.sample_rate = wf.getframerate()
                    raw = wf.readframes(wf.getnframes())
            except Exception as exc:
                logger.warning("Piper synthesis failed for %.60r: %s", text, exc)
                return None
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return samples if _has_audio(samples) else None


class StreamingSpeaker:
    """Queue-based playback loop with gapless sentence streaming."""

    def __init__(self, engine: PiperEngine):
        self._engine = engine
        self._audio_q: "queue.Queue[np.ndarray]" = queue.Queue()
        self._play_thread: Optional[threading.Thread] = None
        self._play_lock = threading.Lock()
        self._running = False
        self._stop_event = threading.Event()
        self._last_play_finish: float = time.monotonic()
        self._last_play_start: float = time.monotonic()

    # -- public API ------------------------------------------------------

    def feed(self, text: str) -> int:
        """Synthesize *text* in the calling thread and enqueue audio.

        Splits into sentences so the first one can reach the speaker ASAP.
        Returns the number of audio chunks enqueued.
        """
        sentences = _split_sentences(text)
        enqueued = 0
        for sent in sentences:
            samples = self._engine.synthesize(sent)
            if samples is not None and len(samples) > 0:
                self._audio_q.put(samples)
                enqueued += 1
        if enqueued and not self._ensure_player():
            logger.warning("Could not start playback for %.60r", text)
        return enqueued

    def speak(self, text: str, blocking: bool = False) -> None:
        """Synthesize and play *text*. Non-blocking unless asked."""
        if not self._ensure_player():
            return
        self.feed(text)
        if blocking:
            self.wait_until_done()

    def feed_async(self, text: str) -> None:
        """Synthesize *text* on a background thread and enqueue audio."""
        threading.Thread(target=self.feed, args=(text,), daemon=True).start()

    def wait_until_done(self, timeout: float = 60.0) -> None:
        """Block until all queued audio has been played out.

        Uses a timestamp updated by the play loop as the source of truth
        instead of blocking on ``sounddevice`` internals, which can hang on
        some Windows audio drivers.
        """
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if self._audio_q.empty():
                if time.monotonic() - self._last_play_finish > 0.4:
                    return
            time.sleep(0.03)

    def stop(self) -> None:
        """Interrupt synthesis + playback immediately (e.g. on new input)."""
        self._stop_event.set()
        import sounddevice as sd

        try:
            sd.stop()
        except Exception:
            pass
        self._last_play_finish = time.monotonic()
        while not self._audio_q.empty():
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break
        self._stop_event.clear()

    def close(self) -> None:
        self._stop_event.set()
        import sounddevice as sd

        try:
            sd.stop()
        except Exception:
            pass
        self._running = False
        self._play_thread = None
        self._last_play_finish = time.monotonic()

    # -- internals -------------------------------------------------------

    def _synth_in_flight(self) -> bool:
        return False

    def _ensure_player(self) -> bool:
        with self._play_lock:
            if self._play_thread is not None and self._play_thread.is_alive():
                return True
            if self._engine.sample_rate <= 0:
                return False
            self._running = True
            self._play_thread = threading.Thread(
                target=self._play_loop, daemon=True, name="piper-speaker"
            )
            self._play_thread.start()
            return True

    def _play_loop(self) -> None:
        import sounddevice as sd

        while self._running and not self._stop_event.is_set():
            try:
                samples = self._audio_q.get(timeout=0.15)
            except queue.Empty:
                continue
            duration = len(samples) / float(self._engine.sample_rate)
            try:
                self._last_play_start = time.monotonic()
                sd.play(samples, self._engine.sample_rate)
                deadline = time.monotonic() + duration + 1.5
                while time.monotonic() < deadline:
                    if self._stop_event.is_set():
                        break
                    try:
                        stream = sd.get_stream()
                    except RuntimeError:
                        break
                    if stream is None or not stream.active:
                        break
                    time.sleep(0.02)
            except Exception as exc:
                logger.debug("Playback interrupted: %s", exc)
            self._last_play_finish = time.monotonic()


_engine = None
_speaker = None
_engine_lock = threading.Lock()


def get_piper_engine(model_path: str) -> PiperEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = PiperEngine(model_path)
    return _engine


def get_speaker(model_path: Optional[str] = None) -> StreamingSpeaker:
    global _speaker
    if _speaker is None:
        if model_path is None:
            raise ValueError("model_path required for first load")
        engine = get_piper_engine(model_path)
        with _engine_lock:
            if _speaker is None:
                _speaker = StreamingSpeaker(engine)
    return _speaker