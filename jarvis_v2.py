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

import json
import logging
import ollama
import os
import subprocess
import sys
import time
import sounddevice as sd
from faster_whisper import WhisperModel
from scipy.io.wavfile import write
from settings_manager import settings
from plugins import PluginManager
from plugins.agents import get_orchestrator
from memory_v2 import get_memory

# Add src folder to sys.path to resolve internal jarvis packages
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from jarvis.speech.playback import play_wav_async, stop_sound


from reminders import start_checker
from planner import plan_action, execute_plan
from task_executor import set_executor_context, register_default_handlers
import memory_v2
from fast_router import FastCommandRouter
from jarvis.speech.playback import wait_for_playback

# For backward compatibility, create a wrapper for the old memory API
class LegacyMemoryWrapper:
    def __init__(self, memory_module):
        self._memory = memory_module
    
    def load(self) -> dict:
        """Backward compatibility wrapper."""
        return self._memory.load()
    
    def save(self, data: dict) -> None:
        """Backward compatibility wrapper."""
        return self._memory.save(data)

# Create legacy wrapper
memory_mod = LegacyMemoryWrapper(memory_v2.get_memory())

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
# Config
# ---------------------------------------------------------------------------
PIPER = settings.get("paths.piper_exe")
VOICE = settings.get("paths.voice_model")
CHAT_MODEL = settings.get("models.chat_model")
SCREENSHOT_DIR = settings.get("paths.screenshot_dir")

WAKE_PHRASES = settings.get("voice.wake_phrases", ["i'm back"])

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
SYSTEM_PROMPT = settings.get("system.system_prompt")

chat_history: list = []  # session-only; bounded below
CHAT_HISTORY_LIMIT = settings.get("voice.chat_history_limit", 10)

# Cached system prompt to avoid reloading memory on every chat call
_facts_cache: tuple = (0.0, "")  # (timestamp, cached_prompt)
_FACTS_CACHE_TTL = 5.0  # seconds


def _build_system_prompt() -> str:
    global _facts_cache
    now = time.time()
    if now - _facts_cache[0] < _FACTS_CACHE_TTL:
        return _facts_cache[1]
    
    facts = memory_mod.load().get("facts", [])
    if not facts:
        result = SYSTEM_PROMPT
    else:
        facts_str = "\n".join(f"- {f}" for f in facts)
        result = (
            SYSTEM_PROMPT
            + "\nHere are facts you remember about Harshith:\n"
            + facts_str
        )
    _facts_cache = (now, result)
    return result


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
    
    # Use a unique filename for each TTS generation to allow concurrent file handling
    wav_filename = f"response_{int(time.time() * 1000)}.wav"
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            [PIPER, "-m", VOICE, "-f", wav_filename],
            input=clean, text=True, capture_output=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.warning("TTS timed out for text: %s", clean[:50])
        return
    except Exception as exc:
        logger.warning("TTS subprocess failed: %s", exc)
        return
    if result.returncode != 0:
        print(result.stderr.decode(errors="ignore"))
        return
    t_tts = time.perf_counter()
    print(f"[TIMING] TTS Gen: {t_tts - t0:.3f}s")
    
    # Play synchronously to guarantee playback before next listen
    play_wav_async(wav_filename)
    wait_for_playback()

# ---------------------------------------------------------------------------
# Audio capture
# ---------------------------------------------------------------------------
import numpy as np

def record_audio(filename: str, seconds: int) -> None:
    # Immediately interrupt any currently playing TTS
    stop_sound()
    fs = 16000
    try:
        recording = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype="int16")
        sd.wait()
        write(filename, fs, recording)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        logger.error("Recording error: %s", exc)


def record_until_silence(filename: str, silence_duration: float = 1.5, threshold: float = 0.02, fs: int = 16000) -> None:
    # Immediately interrupt any currently playing TTS
    stop_sound()
    chunk = int(fs * 0.2)
    audio_chunks = []
    silent_chunks = 0
    silence_chunk_limit = int(silence_duration / 0.2)
    started = False

    def callback(indata, frames, time_info, status):
        nonlocal silent_chunks, started
        volume = np.linalg.norm(indata) / np.sqrt(len(indata))
        if volume > threshold:
            if not started:
                started = True
            silent_chunks = 0
            audio_chunks.append(indata.copy())
        elif started:
            silent_chunks += 1
            audio_chunks.append(indata.copy())

    with sd.InputStream(samplerate=fs, channels=1, dtype="float32", callback=callback, blocksize=chunk):
        while not started or silent_chunks < silence_chunk_limit:
            sd.sleep(100)

    if audio_chunks:
        recording = (np.concatenate(audio_chunks) * 32767).astype(np.int16)
        write(filename, fs, recording)

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
        t0 = time.perf_counter()
        record_audio("wake.wav", 2)
        t_vad = time.perf_counter()
        try:
            segments, _ = wake_model.transcribe("wake.wav", language="en")
        except Exception as exc:
            logger.warning("Wake word transcription failed: %s", exc)
            continue
        
        text = " ".join(s.text for s in segments).lower().strip()
        t_stt = time.perf_counter()
        if text:
            print("Heard:", text)
            print(f"[TIMING] VAD: {t_vad - t0:.3f}s, STT: {t_stt - t_vad:.3f}s")
        if any(p in text for p in WAKE_PHRASES):
            print("Wake phrase detected.")
            speak("Systems online, sir. Awaiting instructions.")
            break
    try:
        os.remove("wake.wav")
    except OSError:
        pass


def listen_command(command_model) -> str:
    print("\nListening...")
    t0 = time.perf_counter()
    record_until_silence("command.wav")
    t_vad = time.perf_counter()
    print("Transcribing...")
    try:
        segments, _ = command_model.transcribe("command.wav", language="en")
    except Exception as exc:
        logger.warning("Command transcription failed: %s", exc)
        try:
            os.remove("command.wav")
        except OSError:
            pass
        return ""
    text = " ".join(s.text for s in segments).strip()
    t_stt = time.perf_counter()
    print(f"[TIMING] VAD: {t_vad - t0:.3f}s, STT: {t_stt - t_vad:.3f}s")
    try:
        os.remove("command.wav")
    except OSError:
        pass
    return text

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    # 1. Wire executor context. `chat` is the AI fallback used by the
    #    ai_chat handler, by web_search summarization, and by the
    #    clipboard "summarize" op. `memory` is the persistent fact store.
    context = {
        "speak": speak,
        "apps": INSTALLED_APPS,
        "chat": chat_with_ollama,
        "memory": memory_mod,
        "settings": settings,
    }
    set_executor_context(context)
    register_default_handlers()
    
    fast_router = FastCommandRouter(context)

    # Initialize Plugin Manager
    plugin_manager = PluginManager(context)
    plugin_manager.discover_and_load()
    
    # Register plugin tools into the planner
    plugin_tools = plugin_manager.get_all_tools()
    for action, handler in plugin_tools.items():
        from planner import register_tool
        register_tool(action, handler)

    # 2. Initialize agent orchestrator
    orchestrator = get_orchestrator(context)
    orchestrator.start_all_agents()
    logger.info("Agent orchestrator started with %d agents", len(orchestrator.agents))

    # 3. Reminder checker runs in a background thread; it needs speak()
    #    so it can announce when a reminder fires.
    start_checker(speak)

    # 4. Print startup diagnostics
    try:
        from diagnostics import check_environment, print_report
        report = check_environment()
        print_report(report)
    except Exception as exc:
        logger.warning("Startup diagnostics failed: %s", exc)

    # 5. Load ASR models and run the wake/listen loop.
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
                wait_for_playback()
                break

            t0 = time.perf_counter()
            fast_result = fast_router.route(user)
            t_route = time.perf_counter()
            print(f"[TIMING] Fast Router: {t_route - t0:.3f}s")
            
            if fast_result:
                print("FAST ROUTER RESULT:", fast_result)
                speak(fast_result)
                wait_for_playback()
                continue
                
            plan = plan_action(user)
            t_plan = time.perf_counter()
            print(f"[TIMING] Planner: {t_plan - t_route:.3f}s")
            print("PLAN:", plan)
            try:
                result = execute_plan(plan)
            except Exception as exc2:
                logger.exception("execute_plan crashed")
                speak(f"Something went wrong, sir. {exc2}")
                wait_for_playback()
                continue

            t_exec = time.perf_counter()
            print(f"[TIMING] Executor: {t_exec - t_plan:.3f}s")
            print("RESULT:", result)
            if result:
                speak(result)
                t_tts = time.perf_counter()
                print(f"[TIMING] TTS Init: {t_tts - t_exec:.3f}s")
                wait_for_playback()


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
