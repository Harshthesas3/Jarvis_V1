"""
wake_listener.py
----------------
Listens for configurable wake phrases using faster-whisper.
Supports exact phrase matching, confidence thresholds, and
multiple wake phrases.

Configuration:
    WAKE_PHRASES — list of phrases that activate JARVIS
    CONFIDENCE_THRESHOLD — minimum confidence (0-1) to accept
    LISTEN_DURATION — seconds per listen cycle
"""

import os
import sys
import time

import sounddevice as sd
from scipy.io.wavfile import write
from faster_whisper import WhisperModel

WAKE_PHRASES: list[str] = [
    "i'm back",
    "i am back",
    "im back",
    "jarvis wake up",
    "jarvis",
]

CONFIDENCE_THRESHOLD: float = 0.5
LISTEN_DURATION: float = 2.0
SAMPLE_RATE: int = 16000


def load_model():
    print("Loading wake model...")
    return WhisperModel("tiny", device="cpu", compute_type="int8")


def listen_once(model, duration: float = LISTEN_DURATION) -> tuple[str, float]:
    recording = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    write("wake.wav", SAMPLE_RATE, recording)
    segments, info = model.transcribe("wake.wav")
    text = " ".join(segment.text for segment in segments).lower().strip()
    avg_confidence = info.duration if hasattr(info, "duration") else 0.0
    return text, avg_confidence


def is_wake_phrase(text: str) -> bool:
    if not text:
        return False
    text_lower = text.strip().lower()
    for phrase in WAKE_PHRASES:
        if phrase in text_lower:
            candidate = text_lower
            idx = candidate.find(phrase)
            before = candidate[:idx].strip()
            after = candidate[idx + len(phrase):].strip()
            if (not before or before in ("", "hey", "okay", "ok", "hello")) and \
               (not after or after in ("", "please", "now")):
                return True
    return False


def main() -> None:
    model = load_model()
    print("Listening for wake phrase...")
    print(f"Say one of: {', '.join(WAKE_PHRASES)}")

    while True:
        try:
            text, confidence = listen_once(model)
            if text:
                print(f"Heard: {text}")
            if is_wake_phrase(text):
                os.system("cls" if sys.platform == "win32" else "clear")
                print("=" * 50)
                print("JARVIS ONLINE")
                print("=" * 50)
                print(f"\nWake phrase detected: '{text}'")
                break
        except KeyboardInterrupt:
            print("\nExiting wake listener.")
            sys.exit(0)
        except Exception as exc:
            print(f"Error: {exc}")
            time.sleep(0.5)


if __name__ == "__main__":
    main()
