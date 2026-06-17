"""
jarvis_v2.py
------------
Voice-driven personal assistant. Listens for the wake phrase "I'm back",
then routes each command through `planner.plan_action` -> `task_executor.
execute_plan`. The executor dispatches to registered handlers (time, date,
apps, web search, reminders, calendar, clipboard, screen awareness, etc.)
and returns a TTS-ready string. Conversational fallbacks go through
`chat_with_ollama`.
"""

import os
import logging
import subprocess
import webbrowser
import sounddevice as sd
from scipy.io.wavfile import write
from faster_whisper import WhisperModel
import psutil
import keyboard
import mss
import json
import re
import html
import urllib.request
import urllib.parse
import tkinter as tk
from datetime import datetime
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
import concurrent.futures

import ollama

from reminders import (
    add_reminder,
    list_reminders,
    remove_reminder,
    clear_reminders,
    start_checker,
)
from calendar_engine import create_calendar_event
from planner import plan_action, execute_plan
from task_executor import (
    set_executor_context,
    register_default_handlers,
)
import memory as memory_mod

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("faster_whisper").setLevel(logging.ERROR)
logger = logging.getLogger("jarvis")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PIPER = (
    r"C:\Users\Harshith\AppData\Local\Packages"
    r"\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0"
    r"\LocalCache\local-packages"
    r"\Python312\Scripts\piper.exe"
)
VOICE = r"C:\Users\Harshith\Downloads\en_US-lessac-medium.onnx"
CHAT_MODEL = "qwen3.5:4b"
SCREENSHOT_DIR = "Screenshots"

WAKE_PHRASES = ["i'm back", "i am back", "im back"]

# ---------------------------------------------------------------------------
# Installed apps (best-effort load across common Windows encodings)
# ---------------------------------------------------------------------------
def _load_apps_json() -> list:
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            with open("apps.json", "r", encoding=encoding) as f:
                return json.load(f)
        except Exception:
            continue
    return []


INSTALLED_APPS = _load_apps_json()

# ---------------------------------------------------------------------------
# Chat: rolling session history + persistent memory injection
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are JARVIS.

You are Harshith's personal AI assistant.
Always address Harshith as sir.

Keep answers concise.
Never use emojis.
Never use markdown.
Speak naturally and professionally.
"""

chat_history: list = []  # session-only; bounded below
CHAT_HISTORY_LIMIT = 10


def _build_system_prompt() -> str:
    facts = memory_mod.load().get("facts", [])
    if not facts:
        return SYSTEM_PROMPT
    facts_str = "\n".join(f"- {f}" for f in facts)
    return (
        SYSTEM_PROMPT
        + "\nHere are facts you remember about Harshith:\n"
        + facts_str
    )


def chat_with_ollama(text: str) -> str:
    """Send `text` to the local chat model, keeping a rolling history of
    the last 10 user/assistant turns and injecting the persistent fact
    store into the system prompt on every call."""
    if not text or not text.strip():
        return ""

    chat_history.append({"role": "user", "content": text})
    if len(chat_history) > CHAT_HISTORY_LIMIT * 2:
        chat_history[:] = chat_history[-CHAT_HISTORY_LIMIT * 2:]

    messages = [{"role": "system", "content": _build_system_prompt()}] + chat_history
    try:
        response = ollama.chat(model=CHAT_MODEL, messages=messages)
        reply = response["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_with_ollama failed: %s", exc)
        reply = "I am having trouble reaching the language model, sir."

    chat_history.append({"role": "assistant", "content": reply})
    return reply

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
def speak(text: str) -> None:
    print(f"\nJarvis: {text}")
    if not text:
        return
    clean = text.encode("ascii", errors="ignore").decode().strip()
    if not clean:
        return
    result = subprocess.run(
        [PIPER, "-m", VOICE, "-f", "response.wav"],
        input=clean, text=True, capture_output=True,
    )
    if result.returncode != 0:
        print(result.stderr.decode(errors="ignore"))
        return
    subprocess.run([
        "powershell", "-c",
        "(New-Object Media.SoundPlayer 'response.wav').PlaySync();",
    ])

# ---------------------------------------------------------------------------
# Audio capture
# ---------------------------------------------------------------------------
def record_audio(filename: str, seconds: int) -> None:
    fs = 16000
    try:
        recording = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype="int16")
        sd.wait()
        write(filename, fs, recording)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        logger.error("Recording error: %s", exc)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def _load_models() -> tuple:
    print("Loading models...")
    wake = WhisperModel("tiny", device="cpu", compute_type="int8")
    command = WhisperModel("base", device="cpu", compute_type="int8")
    print("Models loaded.")
    return wake, command

# ---------------------------------------------------------------------------
# Wake / listen
# ---------------------------------------------------------------------------
def wait_for_wake_word(wake_model) -> None:
    print("\nSleeping...")
    print("Say: I'm back")
    while True:
        record_audio("wake.wav", 2)
        segments, _ = wake_model.transcribe("wake.wav", language="en")
        text = " ".join(s.text for s in segments).lower().strip()
        if text:
            print("Heard:", text)
        if any(p in text for p in WAKE_PHRASES):
            print("Wake phrase detected.")
            speak("Systems online, sir. Awaiting instructions.")
            return


def listen_command(command_model) -> str:
    print("\nListening...")
    record_audio("command.wav", 5)
    print("Transcribing...")
    segments, _ = command_model.transcribe("command.wav", language="en")
    return " ".join(s.text for s in segments).strip()

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    # 1. Wire executor context. `chat` is the AI fallback used by the
    #    ai_chat handler, by web_search summarization, and by the
    #    clipboard "summarize" op. `memory` is the persistent fact store.
    set_executor_context({
        "speak": speak,
        "apps": INSTALLED_APPS,
        "chat": chat_with_ollama,
        "memory": memory_mod,
    })
    register_default_handlers()

    # 2. Reminder checker runs in a background thread; it needs speak()
    #    so it can announce when a reminder fires.
    start_checker(speak)

    # 3. Print startup diagnostics
    try:
        from diagnostics import check_environment, print_report
        report = check_environment()
        print_report(report)
    except Exception as exc:
        logger.warning("Startup diagnostics failed: %s", exc)

    # 4. Load ASR models and run the wake/listen loop.
    wake_model, command_model = _load_models()
    print("\nJARVIS READY")

    while True:
        wait_for_wake_word(wake_model)
        while True:
            user = listen_command(command_model)
            print("\nYou said:", user)
            if not user:
                continue

            # Sleep / goodbye
            user_lower = user.lower()
            if (
                "go to sleep" in user_lower
                or "goodbye" in user_lower
                or "bye jarvis" in user_lower
                or "thank you bye" in user_lower
            ):
                speak("Goodbye sir. Entering standby mode.")
                break

            plan = plan_action(user)
            print("PLAN:", plan)
            try:
                result = execute_plan(plan)
            except Exception as exc:  # noqa: BLE001
                logger.exception("execute_plan crashed")
                speak(f"Something went wrong, sir. {exc}")
                continue
            print("RESULT:", result)
            if result:
                speak(result)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Shutting down gracefully, sir.")
    except Exception as exc:
        logger.exception("Unhandled exception in main: %s", exc)
        try:
            speak(f"Critical error, sir. {exc}")
        except Exception:
            pass
