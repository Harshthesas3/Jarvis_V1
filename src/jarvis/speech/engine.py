"""High-level speech engine combining STT and TTS for a voice interaction loop."""

from __future__ import annotations

import logging
import time
from typing import Optional

from jarvis.interfaces.speech import ASREngine, TTSEngine, WakeWordEngine
from jarvis.speech.stt import SttEngine
from jarvis.speech.tts import TtsEngine
from jarvis.types import AudioChunk, TranscriptResult

logger = logging.getLogger("jarvis.speech.engine")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SAMPLE_RATE = 16000
_DEFAULT_CHUNK_MS = 100  # milliseconds per audio chunk
_DEFAULT_SILENCE_TIMEOUT_MS = 2000
_DEFAULT_MAX_COMMAND_MS = 15000


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SpeechEngine:
    """Full voice interaction engine that combines STT and TTS.

    Coordinates wake-word listening, command capture, and speech
    synthesis so that a caller can run a complete voice loop::

        engine = SpeechEngine(stt=SttEngine(), tts=TtsEngine())

        while True:
            engine.wait_for_wake_word()
            command = engine.capture_command()
            response = process_command(command)
            engine.speak(response)
    """

    def __init__(
        self,
        stt: Optional[ASREngine] = None,
        tts: Optional[TTSEngine] = None,
        wake_word_engine: Optional[WakeWordEngine] = None,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        silence_timeout_ms: int = _DEFAULT_SILENCE_TIMEOUT_MS,
        max_command_ms: int = _DEFAULT_MAX_COMMAND_MS,
    ) -> None:
        self._stt = stt or SttEngine()
        self._tts = tts or TtsEngine()
        self._wake = wake_word_engine
        self._sample_rate = sample_rate
        self._silence_timeout_ms = silence_timeout_ms
        self._max_command_ms = max_command_ms

        self._running = False
        self._listening = False

        logger.info(
            "SpeechEngine(sr=%d, silence=%dms, max_cmd=%dms)",
            sample_rate,
            silence_timeout_ms,
            max_command_ms,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def wait_for_wake_word(
        self,
        phrases: Optional[list[str]] = None,
        stream_source: Optional[AudioStream] = None,
    ) -> AudioChunk:
        """Block until the wake word is detected.

        Reads audio from *stream_source* (or a default microphone stream)
        and feeds it to the wake-word detector.  Returns the audio chunk
        that triggered the detection.
        """
        if self._wake is not None:
            return self._wait_wakeword(phrases, stream_source)

        # Fall back to transcribe-loop using the STT engine.
        return self._wait_stt_loop(phrases, stream_source)

    def capture_command(
        self,
        stream_source: Optional[AudioStream] = None,
    ) -> str:
        """Record audio until silence, then transcribe and return the text.

        Uses voice-activity detection to determine when the user has
        stopped speaking.  Returns the transcribed command string.
        """
        audio_chunks = self._record_until_silence(stream_source)
        if not audio_chunks:
            return ""

        merged = self._merge_chunks(audio_chunks)
        result = self._stt.transcribe(merged)
        logger.info("Captured command: '%s' (conf=%.3f)", result.text, result.confidence)
        return result.text

    def speak(self, text: str, blocking: bool = True) -> None:
        """Synthesize and play *text* via the TTS engine.

        Args:
            text: The text to speak.
            blocking: If ``True`` (default), block until speech finishes.
        """
        if blocking:
            self._tts.speak(text)
        else:
            self._tts.speak_async(text)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether both STT and TTS engines are available."""
        stt_ok = self._stt.is_available() if hasattr(self._stt, "is_available") else True
        tts_ok = self._tts.is_available()
        return stt_ok and tts_ok

    def stop(self) -> None:
        """Stop any ongoing listening or speech."""
        self._running = False
        self._listening = False
        self._tts.stop()

    # ------------------------------------------------------------------
    # Wake-word detection strategies
    # ------------------------------------------------------------------

    def _wait_wakeword(
        self,
        phrases: Optional[list[str]],
        stream_source: Optional[AudioStream],
    ) -> AudioChunk:
        """Use the dedicated WakeWordEngine if one was provided."""
        assert self._wake is not None

        if phrases:
            self._wake.set_phrases(phrases)
        self._wake.reset()

        stream = stream_source or _mic_stream(self._sample_rate)
        self._listening = True

        try:
            for chunk in stream:
                if not self._listening:
                    raise StopIteration("Listening was stopped.")
                if self._wake.process_chunk(chunk):
                    logger.info("Wake word detected via WakeWordEngine")
                    return chunk
        finally:
            self._listening = False

        raise RuntimeError("Audio stream ended before wake word detected")

    def _wait_stt_loop(
        self,
        phrases: Optional[list[str]],
        stream_source: Optional[AudioStream],
    ) -> AudioChunk:
        """Fallback: poll the STT engine for wake phrases in a loop."""
        wake_phrases = phrases or getattr(self._stt, "wake_phrases", ["jarvis"])
        stream = stream_source or _mic_stream(self._sample_rate)
        self._listening = True

        try:
            for chunk in stream:
                if not self._listening:
                    raise StopIteration("Listening was stopped.")

                if hasattr(self._stt, "detect_wake_word"):
                    if self._stt.detect_wake_word(chunk, phrases=wake_phrases):  # type: ignore[union-attr]
                        return chunk
                else:
                    # Generic: transcribe and check.
                    result = self._stt.transcribe(chunk)
                    if result.is_wake_word:
                        return chunk
                    for phrase in wake_phrases:
                        if phrase.lower() in result.text.lower():
                            return chunk
        finally:
            self._listening = False

        raise RuntimeError("Audio stream ended before wake word detected")

    # ------------------------------------------------------------------
    # Command capture internals
    # ------------------------------------------------------------------

    def _record_until_silence(
        self,
        stream_source: Optional[AudioStream],
    ) -> list[AudioChunk]:
        """Record audio chunks until silence is detected or timeout reached."""
        stream = stream_source or _mic_stream(self._sample_rate)
        chunks: list[AudioChunk] = []

        silence_start: Optional[float] = None
        command_start = time.monotonic()

        self._listening = True

        try:
            for chunk in stream:
                if not self._listening:
                    break

                elapsed = (time.monotonic() - command_start) * 1000.0
                if elapsed > self._max_command_ms:
                    logger.debug("Command capture reached max duration (%dms)", self._max_command_ms)
                    break

                chunks.append(chunk)

                # Simple energy-based VAD
                if _is_silent(chunk):
                    if silence_start is None:
                        silence_start = time.monotonic()
                    elif (time.monotonic() - silence_start) * 1000.0 > self._silence_timeout_ms:
                        logger.debug("Silence timeout reached (%dms)", self._silence_timeout_ms)
                        break
                else:
                    silence_start = None
        finally:
            self._listening = False

        return chunks

    @staticmethod
    def _merge_chunks(chunks: list[AudioChunk]) -> AudioChunk:
        """Concatenate a list of AudioChunks into a single chunk."""
        if not chunks:
            return AudioChunk(data=b"", sample_rate=_DEFAULT_SAMPLE_RATE)

        data = b"".join(c.data for c in chunks)
        return AudioChunk(
            data=data,
            sample_rate=chunks[0].sample_rate,
            channels=chunks[0].channels,
            dtype=chunks[0].dtype,
            timestamp=chunks[0].timestamp,
        )


# ---------------------------------------------------------------------------
# Microphone stream abstraction
# ---------------------------------------------------------------------------


class AudioStream:
    """Minimal iterable wrapper around a microphone input stream.

    Yields :class:`~jarvis.types.AudioChunk` objects until the stream
    is closed or exhausted.
    """

    def __init__(
        self,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        chunk_ms: int = _DEFAULT_CHUNK_MS,
    ) -> None:
        self._sample_rate = sample_rate
        self._chunk_size = int(sample_rate * chunk_ms / 1000)
        self._closed = False

    def __iter__(self):
        return self._iter()

    def _iter(self):
        """Generator that reads from the microphone."""
        try:
            import pyaudio
        except ImportError:
            logger.error("pyaudio is required for microphone input")
            return

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=self._chunk_size,
        )

        try:
            while not self._closed:
                raw = stream.read(self._chunk_size, exception_on_overflow=False)
                yield AudioChunk(
                    data=raw,
                    sample_rate=self._sample_rate,
                    channels=1,
                    dtype="int16",
                    timestamp=time.time(),
                )
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()

    def close(self) -> None:
        self._closed = True


# ---------------------------------------------------------------------------
# Module-level convenience factory
# ---------------------------------------------------------------------------


def _mic_stream(sample_rate: int = _DEFAULT_SAMPLE_RATE) -> AudioStream:
    """Create an :class:`AudioStream` reading from the default microphone."""
    return AudioStream(sample_rate=sample_rate)


# ---------------------------------------------------------------------------
# Voice activity detection
# ---------------------------------------------------------------------------


def _is_silent(chunk: AudioChunk, threshold: float = 0.02) -> bool:
    """Heuristic energy-based silence detection.

    Returns ``True`` if the RMS energy of *chunk* is below *threshold*.
    """
    import numpy as np

    raw = np.frombuffer(chunk.data, dtype=np.int16).astype(np.float32)
    if len(raw) == 0:
        return True
    rms = np.sqrt(np.mean(raw ** 2))
    normalized = rms / 32768.0
    return normalized < threshold
