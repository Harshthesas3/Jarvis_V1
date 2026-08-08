"""Speech-to-text engine using faster_whisper."""

from __future__ import annotations

import logging
import os
import tempfile
import wave
from pathlib import Path
from typing import Optional

from jarvis.interfaces.speech import ASREngine, WakeWordEngine
from jarvis.types import AudioChunk, TranscriptResult

logger = logging.getLogger("jarvis.speech.stt")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_WAKE_PHRASES = ["jarvis", "hey jarvis"]
_TINY_MODEL_SIZE = "tiny"
# distil-small.en is ~3x faster than base on CPU with equal English accuracy.
# Falls back to "base" automatically if the distil model is not cached.
_DISTIL_COMMAND_MODEL = "Systran/faster-distil-whisper-small.en"
_BASE_MODEL_SIZE = "base"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _audio_to_float(audio: AudioChunk):
    """Convert AudioChunk int16 bytes to float32 numpy array."""
    import numpy as np
    raw = np.frombuffer(audio.data, dtype=np.dtype(audio.dtype))
    return raw.astype(np.float32) / 32768.0


def _write_temp_wav(audio: AudioChunk) -> str:
    """Write an AudioChunk to a temporary WAV file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(audio.channels)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(audio.sample_rate)
        wf.writeframes(audio.data)
    return path


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SttEngine(ASREngine):
    """Speech-to-text engine powered by faster_whisper.

    Uses a small "tiny" model for wake-word detection and a "base" model
    for full command transcription. Both models are loaded lazily so that
    the engine can start with minimal memory overhead.
    """

    def __init__(
        self,
        wake_model_size: str = _TINY_MODEL_SIZE,
        command_model_size: str = _DISTIL_COMMAND_MODEL,
        device: str = "auto",
        compute_type: str = "int8",
        wake_phrases: Optional[list[str]] = None,
        model_dir: Optional[str] = None,
    ) -> None:
        self._wake_model_size = wake_model_size
        self._command_model_size = command_model_size
        self._device = device
        self._compute_type = compute_type
        self._wake_phrases = wake_phrases or list(_DEFAULT_WAKE_PHRASES)
        self._model_dir = model_dir

        self._wake_model = None
        self._command_model = None
        self._available = False

        logger.info(
            "SttEngine(wake=%s, command=%s, device=%s, compute=%s)",
            wake_model_size,
            command_model_size,
            device,
            compute_type,
        )

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def _load_wake_model(self):
        """Load the small wake-word detection model (lazy)."""
        if self._wake_model is not None:
            return
        try:
            from faster_whisper import WhisperModel

            self._wake_model = WhisperModel(
                self._wake_model_size,
                device=self._device,
                compute_type=self._compute_type,
                download_root=self._model_dir,
            )
            self._available = True
            logger.info("Loaded wake-word model '%s'", self._wake_model_size)
        except Exception:
            logger.exception("Failed to load wake-word model '%s'", self._wake_model_size)
            raise

    def _load_command_model(self):
        """Load the larger command transcription model (lazy)."""
        if self._command_model is not None:
            return
        try:
            from faster_whisper import WhisperModel

            self._command_model = WhisperModel(
                self._command_model_size,
                device=self._device,
                compute_type=self._compute_type,
                download_root=self._model_dir,
            )
            self._available = True
            logger.info("Loaded command model '%s'", self._command_model_size)
        except Exception:
            logger.exception("Failed to load command model '%s'", self._command_model_size)
            raise

    # ------------------------------------------------------------------
    # ASREngine interface
    # ------------------------------------------------------------------

    def transcribe(self, audio: AudioChunk) -> TranscriptResult:
        """Transcribe a single audio chunk to text using the command model."""
        self._load_command_model()
        assert self._command_model is not None

        audio_array = _audio_to_float(audio)

        segments, info = self._command_model.transcribe(
            audio_array,
            beam_size=5,
            language="en",
            vad_filter=True,
        )

        text_parts: list[str] = []
        best_confidence = 0.0
        duration_ms = 0.0

        for seg in segments:
            text_parts.append(seg.text.strip())
            if seg.avg_logprob is not None:
                # Convert average logprob to a pseudo-confidence score (0-1).
                confidence = max(0.0, min(1.0, 2.0 ** seg.avg_logprob))
                best_confidence = max(best_confidence, confidence)
            duration_ms = max(duration_ms, (seg.end - seg.start) * 1000.0)

        text = " ".join(text_parts)

        logger.debug("Transcribed %d bytes -> '%s' (conf=%.3f)", len(audio.data), text, best_confidence)

        return TranscriptResult(
            text=text,
            confidence=best_confidence,
            language=info.language if info else "en",
            is_wake_word=False,
            duration_ms=duration_ms,
        )

    def transcribe_file(self, path: str) -> TranscriptResult:
        """Transcribe audio from a WAV file."""
        self._load_command_model()
        assert self._command_model is not None

        audio_array = _load_audio_from_file(path)

        segments, info = self._command_model.transcribe(
            audio_array,
            beam_size=5,
            language="en",
            vad_filter=True,
        )

        text_parts: list[str] = []
        best_confidence = 0.0
        duration_ms = 0.0

        for seg in segments:
            text_parts.append(seg.text.strip())
            if seg.avg_logprob is not None:
                confidence = max(0.0, min(1.0, 2.0 ** seg.avg_logprob))
                best_confidence = max(best_confidence, confidence)
            duration_ms = max(duration_ms, (seg.end - seg.start) * 1000.0)

        text = " ".join(text_parts)

        return TranscriptResult(
            text=text,
            confidence=best_confidence,
            language=info.language if info else "en",
            is_wake_word=False,
            duration_ms=duration_ms,
        )

    def is_available(self) -> bool:
        """Check whether the faster_whisper models are loaded and usable."""
        if not self._available:
            try:
                self._load_wake_model()
            except Exception:
                return False
        return self._available

    # ------------------------------------------------------------------
    # Wake-word detection (additional, not on ASREngine)
    # ------------------------------------------------------------------

    def detect_wake_word(
        self,
        audio: AudioChunk,
        phrases: Optional[list[str]] = None,
    ) -> bool:
        """Detect whether *audio* contains one of the configured wake phrases.

        Uses the tiny whisper model and checks transcribed text against the
        wake-phrase list.  Returns ``True`` as soon as any phrase matches.
        """
        self._load_wake_model()
        assert self._wake_model is not None

        phrases = phrases or self._wake_phrases
        audio_array = _audio_to_float(audio)

        segments, _ = self._wake_model.transcribe(
            audio_array,
            beam_size=3,
            language="en",
            vad_filter=False,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )

        for seg in segments:
            transcript = seg.text.strip().lower()
            for phrase in phrases:
                if phrase.lower() in transcript:
                    logger.info("Wake word detected (phrase='%s')", phrase)
                    return True

        return False

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @property
    def wake_phrases(self) -> list[str]:
        return list(self._wake_phrases)

    @wake_phrases.setter
    def wake_phrases(self, phrases: list[str]) -> None:
        self._wake_phrases = list(phrases)


# ---------------------------------------------------------------------------
# File-based helper (kept separate to avoid cluttering the class)
# ---------------------------------------------------------------------------


def _load_audio_from_file(path: str):
    """Load a WAV file and return a float32 mono array."""
    import numpy as np
    import soundfile as sf

    audio_array, _ = sf.read(path, dtype="float32")
    if audio_array.ndim > 1:
        audio_array = np.mean(audio_array, axis=1)
    return audio_array
