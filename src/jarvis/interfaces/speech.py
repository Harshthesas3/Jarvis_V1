"""Speech recognition and synthesis interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from jarvis.types import AudioChunk, TranscriptResult


class ASREngine(ABC):
    """Automatic Speech Recognition interface."""

    @abstractmethod
    def transcribe(self, audio: AudioChunk) -> TranscriptResult:
        """Transcribe a single audio chunk to text."""

    @abstractmethod
    def transcribe_file(self, path: str) -> TranscriptResult:
        """Transcribe audio from a WAV file."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the ASR engine is ready."""


class WakeWordEngine(ABC):
    """Wake word detection interface."""

    @abstractmethod
    def process_chunk(self, audio: AudioChunk) -> bool:
        """Process an audio chunk. Returns True if wake word detected."""

    @abstractmethod
    def set_phrases(self, phrases: list[str]) -> None:
        """Update the wake phrases to listen for."""

    @abstractmethod
    def reset(self) -> None:
        """Reset the detector state."""


class TTSEngine(ABC):
    """Text-to-Speech synthesis interface."""

    @abstractmethod
    def speak(self, text: str) -> None:
        """Synthesize and play text as speech."""

    @abstractmethod
    def speak_async(self, text: str) -> None:
        """Non-blocking speech synthesis."""

    @abstractmethod
    def synthesize(self, text: str, output_path: str) -> bool:
        """Synthesize text to a WAV file without playing."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the TTS engine is ready."""

    @abstractmethod
    def stop(self) -> None:
        """Stop any ongoing speech synthesis."""
