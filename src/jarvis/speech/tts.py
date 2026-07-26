"""Text-to-speech engine using Piper TTS."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Optional

from jarvis.interfaces.speech import TTSEngine

logger = logging.getLogger("jarvis.speech.tts")

from jarvis.speech.playback import play_wav_async, stop_sound, wait_for_playback


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PIPER_DEFAULT_RATE = 16000
_PIPER_DEFAULT_VOICE = "en_US-lessac-medium"


def _find_piper_binary() -> Optional[str]:
    """Locate the ``piper`` executable on ``PATH`` or at common locations."""
    candidates = [
        "piper",
        "piper.exe",
        "piper-tts",
        os.path.expanduser("~/.piper/piper"),
        os.path.expanduser("~/.piper/piper.exe"),
        "/usr/bin/piper",
        "/usr/local/bin/piper",
    ]
    for candidate in candidates:
        if candidate.startswith(("~", "/", "C:", "D:")):
            if os.path.isfile(candidate):
                return candidate
        else:
            try:
                import shutil

                resolved = shutil.which(candidate)
                if resolved:
                    return resolved
            except Exception:
                pass
    return None


def _find_voice_model(name: str, model_dir: Optional[str] = None) -> Optional[str]:
    """Look for a Piper voice model file by name."""
    search_dirs = [
        model_dir,
        os.path.expanduser("~/.piper/voices"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "piper"),
    ]
    search_dirs = [d for d in search_dirs if d is not None]

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for candidate in (name, f"{name}.onnx", f"{name}.json"):
            path = os.path.join(directory, candidate)
            if os.path.isfile(path):
                return path
            # Also check for .onnx without providing extension
            onnx_path = os.path.join(directory, f"{name}.onnx")
            if candidate == name and os.path.isfile(onnx_path):
                return onnx_path

    return None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TtsEngine(TTSEngine):
    """Text-to-speech engine backed by Piper TTS.

    Piper is a fast, local neural TTS system that runs on CPU.
    Voice models (``.onnx`` + ``.json``) must be downloaded separately,
    for example from https://rhasspy.github.io/piper-samples/.
    """

    def __init__(
        self,
        voice: str = _PIPER_DEFAULT_VOICE,
        rate: int = _PIPER_DEFAULT_RATE,
        piper_path: Optional[str] = None,
        model_dir: Optional[str] = None,
        play_command: Optional[str] = None,
    ) -> None:
        self._voice = voice
        self._rate = rate
        self._piper_path = piper_path or _find_piper_binary()
        self._model_dir = model_dir
        self._play_command = play_command or _detect_play_command()

        self._voice_path: Optional[str] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._speak_thread: Optional[threading.Thread] = None

        logger.info(
            "TtsEngine(voice=%s, piper=%s, play=%s)",
            voice,
            self._piper_path,
            self._play_command,
        )

    # ------------------------------------------------------------------
    # TTSEngine interface
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Synthesize and play *text* as speech."""
        if not text.strip():
            return

        wav_path = None
        try:
            import time
            # Generate a unique path for the synthesized WAV file
            fd, wav_path = tempfile.mkstemp(suffix=f"_{int(time.time() * 1000)}.wav")
            os.close(fd)
            
            res = self.synthesize(text, output_path=wav_path)
            if res and os.path.isfile(res):
                self._play_wav(res)
        except Exception:
            logger.exception("Failed to speak text: '%s'", text[:60])
            if wav_path and os.path.isfile(wav_path):
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

    def speak_async(self, text: str) -> None:
        """Synthesize and play *text* in a background thread."""
        if not text.strip():
            return
        self._stop_event.clear()
        self._speak_thread = threading.Thread(
            target=self.speak,
            args=(text,),
            daemon=True,
        )
        self._speak_thread.start()

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        """Synthesize *text* to a WAV file.

        If *output_path* is ``None`` a temporary file is created.
        Returns the path to the generated WAV, or ``None`` on failure.
        """
        if not text.strip():
            return output_path

        resolved = self._resolve_voice()
        if not resolved:
            logger.error("Piper voice model not found for '%s'", self._voice)
            return None

        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)

        cmd = [
            self._piper_path,
            "--model", resolved,
            "--output-file", output_path,
            "--length-scale", "1.0",
            "--sentence-silence", "0.3",
        ]

        logger.debug("Running piper: %s", " ".join(str(c) for c in cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            _, stderr_data = proc.communicate(input=text.encode("utf-8"), timeout=120)
            if proc.returncode != 0:
                logger.error(
                    "Piper exited with code %d: %s",
                    proc.returncode,
                    stderr_data.decode(errors="replace").strip(),
                )
                return None
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            logger.error("Piper timed out for text: '%s'", text[:60])
            return None
        except FileNotFoundError:
            logger.error("Piper binary not found at '%s'", self._piper_path)
            return None

        return output_path

    def is_available(self) -> bool:
        """Check whether the Piper binary and voice model are accessible."""
        if not self._piper_path or not os.path.isfile(self._piper_path):
            return False
        if not self._resolve_voice():
            return False
        return True

    def stop(self) -> None:
        """Stop any ongoing speech synthesis."""
        self._stop_event.set()
        if self._speak_thread and self._speak_thread.is_alive():
            self._speak_thread.join(timeout=5)
            self._speak_thread = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_voice(self) -> Optional[str]:
        """Resolve the voice model path, caching the result."""
        if self._voice_path is not None:
            return self._voice_path

        resolved = _find_voice_model(self._voice, self._model_dir)
        if resolved:
            self._voice_path = resolved
            logger.info("Resolved voice model: %s", resolved)
        return self._voice_path

    def _play_wav(self, path: str) -> None:
        """Play a WAV file and wait for completion on Windows, or fallback to subprocess play command on Linux."""
        import platform
        if platform.system().lower() == "windows":
            play_wav_async(path)
            wait_for_playback()  # Block until audio finishes so it isn't cut off
            return

        cmd = _build_play_cmd(self._play_command, path)
        if not cmd:
            logger.warning("No audio player available to play '%s'", path)
            try:
                os.unlink(path)
            except OSError:
                pass
            return

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Audio player timed out for '%s'", path)
        except Exception:
            logger.exception("Audio player failed for '%s'", path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Platform-specific helpers
# ---------------------------------------------------------------------------


def _detect_play_command() -> str:
    """Detect the best available audio playback command for the current OS."""
    import platform as _platform
    import shutil

    system = _platform.system().lower()

    if system == "windows":
        # Windows can use powershell to play audio.
        return "powershell"

    for cmd in ("aplay", "paplay", "ffplay", "play"):
        if shutil.which(cmd):
            return cmd

    # Fallback — modern Linux with pipewire/pulse.
    if shutil.which("pw-play"):
        return "pw-play"

    return ""


def _build_play_cmd(play_command: str, wav_path: str) -> Optional[list[str]]:
    """Build the subprocess command list for the given audio player."""
    if not play_command:
        return None

    command_map: dict[str, list[str]] = {
        "aplay": ["aplay", wav_path],
        "paplay": ["paplay", wav_path],
        "ffplay": ["ffplay", "-nodisp", "-autoexit", wav_path],
        "play": ["play", wav_path],
        "pw-play": ["pw-play", wav_path],
        "powershell": [
            "powershell",
            "-c",
            f'(New-Object Media.SoundPlayer "{wav_path}").PlaySync()',
        ],
    }

    return command_map.get(play_command, [play_command, wav_path])
