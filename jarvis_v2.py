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
import os
import subprocess
import sys
import threading
import time
from settings_manager import settings
from plugins import PluginManager
from plugins.agents import get_orchestrator

# Add src folder to sys.path to resolve internal jarvis packages
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from jarvis.speech.playback import stop_sound


from reminders import start_checker
from planner import plan_action, execute_plan
from task_executor import set_executor_context, register_default_handlers
from fast_router import FastCommandRouter

# For backward compatibility, create a wrapper for the old memory API
class LegacyMemoryWrapper:
    def __init__(self, memory_module=None):
        self._memory = memory_module
        self._load_error = None

    def _get(self):
        if self._memory is None:
            try:
                from memory_v2 import get_memory
                self._memory = get_memory()
            except Exception as exc:  # noqa: BLE001
                self._load_error = exc
        return self._memory

    def load(self) -> dict:
        """Backward compatibility wrapper (lazy: memory_v2 is expensive to import)."""
        mem = self._get()
        if mem is None:
            return {"facts": []}
        return mem.load()

    def save(self, data: dict) -> None:
        """Backward compatibility wrapper."""
        mem = self._get()
        if mem is not None:
            return mem.save(data)

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

# Created lazily; holds the *lazy* wrapper so the heavy memory_v2 module
# (faiss / sentence-transformers imports) does not block startup.
memory_mod = LegacyMemoryWrapper()


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


_LLM_KWARGS = {"keep_alive": -1, "think": False}


def chat_with_ollama(text: str) -> str:
    """Send `text` to the local chat model, keeping a rolling history of
    the last 10 user/assistant turns and injecting the persistent fact
    store into the system prompt on every call."""
    import ollama

    if not text or not text.strip():
        return ""

    chat_history.append({"role": "user", "content": text})
    if len(chat_history) > CHAT_HISTORY_LIMIT * 2:
        chat_history[:] = chat_history[-CHAT_HISTORY_LIMIT * 2:]

    messages = [{"role": "system", "content": _build_system_prompt()}] + chat_history
    try:
        stream = ollama.chat(
            model=CHAT_MODEL,
            messages=messages,
            stream=True,
            options={"num_predict": 150},
            **_LLM_KWARGS,
        )
        reply = "".join(
            chunk.get("message", {}).get("content", "")
            for chunk in stream
            if chunk.get("message", {}).get("content")
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_with_ollama failed: %s", exc)
        reply = "I am having trouble reaching the language model, sir."

    chat_history.append({"role": "assistant", "content": reply})
    return reply


def chat_stream_ollama(text: str, on_text=None):
    """Stream a chat response from the local model.

    Yields content fragments as they arrive (thinking disabled, model pinned
    in memory). ``on_text`` is called with each fragment; the caller can feed
    TTS incrementally so speech overlaps generation.
    """
    import ollama

    if not text or not text.strip():
        return

    chat_history.append({"role": "user", "content": text})
    if len(chat_history) > CHAT_HISTORY_LIMIT * 2:
        chat_history[:] = chat_history[-CHAT_HISTORY_LIMIT * 2:]

    messages = [{"role": "system", "content": _build_system_prompt()}] + chat_history
    reply_parts: list[str] = []
    try:
        stream = ollama.chat(
            model=CHAT_MODEL,
            messages=messages,
            stream=True,
            options={"num_predict": 150},
            **_LLM_KWARGS,
        )
        for chunk in stream:
            frag = chunk.get("message", {}).get("content", "")
            if not frag:
                continue
            reply_parts.append(frag)
            if on_text is not None:
                on_text(frag)
            yield frag
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_stream_ollama failed: %s", exc)
        yield "I am having trouble reaching the language model, sir."
    finally:
        reply = "".join(reply_parts)
        chat_history.append({"role": "assistant", "content": reply})

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
def speak(text: str) -> None:
    """Synthesize and play *text* in-process (non-blocking, gapless).

    Uses :class:`jarvis.speech.piper_rt.StreamingSpeaker`, which keeps the
    Piper ONNX voice loaded once and plays through a persistent audio queue
    (~1 s per sentence instead of ~2.7 s per subprocess utterance).
    """
    print(f"\nJarvis: {text}")
    if not text:
        return
    clean = text.encode("ascii", errors="ignore").decode().strip()
    if not clean:
        return
    from jarvis.speech.piper_rt import get_speaker

    speaker = get_speaker(VOICE)
    speaker.speak(clean, blocking=False)


def wait_until_spoken(timeout: float = 30.0) -> None:
    """Block until the current TTS utterance finishes (compat helper)."""
    from jarvis.speech.piper_rt import get_speaker

    try:
        get_speaker(VOICE).wait_until_done(timeout=timeout)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Audio capture
# ---------------------------------------------------------------------------
import numpy as np


def _mic_chunks(fs: int = 16000, chunk_frames: int = 1600, threshold: float = 0.02):
    """Yield ``(volume, float32_mono_chunk)`` pairs from a persistent mic stream.

    A single InputStream stays open for the whole listen session, which
    removes the per-utterance device open/close overhead of ``sd.rec``.
    """
    import queue as _queue
    import sounddevice as sd

    q = _queue.Queue(maxsize=128)

    def _cb(indata, frames, time_info, status):
        vol = float(np.linalg.norm(indata) / np.sqrt(len(indata)))
        try:
            q.put_nowait((vol, indata.copy()))
        except _queue.Full:
            pass

    with sd.InputStream(
        samplerate=fs, channels=1, dtype="float32",
        callback=_cb, blocksize=chunk_frames,
    ) as _stream:
        while True:
            yield q.get()


def record_audio(filename: str, seconds: int) -> None:
    """Compatibility shim: fixed-length recording written to a WAV file."""
    import sounddevice as sd
    from scipy.io.wavfile import write

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
    """Compatibility shim: capture until silence, write a WAV file."""
    from scipy.io.wavfile import write

    stop_sound()
    chunks = _capture_command_audio(threshold=threshold, fs=fs, max_wait=30)
    if chunks:
        write(filename, fs, (np.concatenate(chunks) * 32767).astype(np.int16))

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def _load_models() -> tuple:
    """Load tiny (wake) + base (command) whisper models in parallel."""
    from concurrent.futures import ThreadPoolExecutor
    from faster_whisper import WhisperModel

    def _load(name: str):
        return WhisperModel(name, device="cpu", compute_type="int8")

    print("Loading models...")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(_load, "tiny")
        f2 = ex.submit(_load, "base")
        wake, command = f1.result(), f2.result()
    print(f"Models loaded. ({(time.perf_counter() - t0) * 1000:.0f} ms)")
    return wake, command


def _transcribe_numpy(model, audio: np.ndarray, *, beam_size: int = 1) -> str:
    """Transcribe an in-memory float32 array (no disk round-trip)."""
    segments, _ = model.transcribe(
        audio,
        language="en",
        beam_size=beam_size,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    return " ".join(s.text for s in segments).strip()


# ---------------------------------------------------------------------------
# Wake / listen
# ---------------------------------------------------------------------------
def wait_for_wake_word(wake_model) -> None:
    print("\nSleeping...")
    print("Say: I'm back")
    chunk_frames = 1600  # 100 ms

    while True:
        buffer: list[np.ndarray] = []
        had_speech = False
        silent_chunks = 0
        speech_chunks = 0

        for vol, data in _mic_chunks(chunk_frames=chunk_frames):
            if vol > 0.02:
                if not had_speech:
                    had_speech = True
                    buffer = []
                buffer.append(data)
                speech_chunks += 1
                silent_chunks = 0
            elif had_speech:
                buffer.append(data)
                silent_chunks += 1

            # Transcribe once we have a complete short utterance:
            # at least 400 ms of speech, then either 700 ms of silence
            # or a hard 2.0 s cap.
            if (
                had_speech
                and speech_chunks >= 4
                and (silent_chunks >= 7 or speech_chunks >= 20)
            ):
                break

        if not buffer:
            continue

        audio = np.concatenate(buffer)
        t0 = time.perf_counter()
        try:
            text = _transcribe_numpy(wake_model, audio)
        except Exception as exc:
            logger.warning("Wake word transcription failed: %s", exc)
            continue
        stt_ms = (time.perf_counter() - t0) * 1000.0

        text_lower = text.lower().strip()
        if text_lower:
            print(f"Heard: {text}  ([STT] {stt_ms:.0f} ms)")
        if any(p in text_lower for p in WAKE_PHRASES):
            print("Wake phrase detected.")
            speak("Systems online, sir. Awaiting instructions.")
            break


def _capture_command_audio(threshold: float = 0.02, fs: int = 16000, max_wait: float = 30.0) -> list[np.ndarray]:
    """Record until silence, returning float32 chunks (never touches disk)."""
    stop_sound()
    chunk_frames = int(fs * 0.1)
    chunks: list[np.ndarray] = []
    started = False
    silent_chunks = 0
    waited = 0
    max_chunks = int(max_wait / 0.1)

    for vol, data in _mic_chunks(fs=fs, chunk_frames=chunk_frames):
        waited += 1
        if vol > threshold:
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
    return chunks


def listen_command(command_model) -> str:
    print("\nListening...")
    chunks = _capture_command_audio()
    if not chunks:
        return ""
    audio = np.concatenate(chunks)
    print("Transcribing...")
    t0 = time.perf_counter()
    try:
        text = _transcribe_numpy(command_model, audio)
    except Exception as exc:
        logger.warning("Command transcription failed: %s", exc)
        return ""
    print(f"[TIMING] STT: {(time.perf_counter() - t0) * 1000:.0f} ms")
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

    # 6. Warm the LLM + piper voice in the background so the first
    #    spoken response doesn't pay cold-start costs.
    def _warmup():
        try:
            t0 = time.perf_counter()
            for _ in chat_stream_ollama("Respond with the single word: ready.", on_text=None):
                pass
            logger.info("LLM warmup complete (%.0f ms)", (time.perf_counter() - t0) * 1000.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM warmup failed: %s", exc)

    def _preload_piper():
        try:
            from jarvis.speech.piper_rt import get_speaker
            get_speaker(VOICE)
            logger.info("Piper voice preloaded")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Piper preload failed: %s", exc)

    threading.Thread(target=_warmup, daemon=True, name="llm-warmup").start()
    threading.Thread(target=_preload_piper, daemon=True, name="piper-preload").start()

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

            t0 = time.perf_counter()
            fast_result = fast_router.route(user)
            t_route = time.perf_counter()
            print(f"[TIMING] Fast Router: {t_route - t0:.3f}s")

            if fast_result:
                print("FAST ROUTER RESULT:", fast_result)
                speak(fast_result)
                continue

            # Regex-only planning (sub-ms). The LLM classify path costs
            # 2-9 s of sequential model calls, which blows the 3 s budget.
            plan = plan_action(user, use_llm=False)
            t_plan = time.perf_counter()
            print(f"[TIMING] Planner: {t_plan - t_route:.3f}s")
            print("PLAN:", plan)

            # Streaming chat: speak the first sentence while the LLM keeps
            # generating instead of waiting for the full response + full TTS.
            if plan.get("action") == "ai_chat":
                if plan.get("_direct_text"):
                    speak(plan.get("text"))
                else:
                    print("STREAMING AI CHAT")
                    _stream_chat_and_speak(user)
                continue

            try:
                result = execute_plan(plan)
            except Exception as exc2:
                logger.exception("execute_plan crashed")
                speak(f"Something went wrong, sir. {exc2}")
                continue

            t_exec = time.perf_counter()
            print(f"[TIMING] Executor: {t_exec - t_plan:.3f}s")
            print("RESULT:", result)
            if result:
                speak(result)


def _stream_chat_and_speak(text: str) -> None:
    """Stream the LLM response and speak each sentence as it completes."""
    import re
    from jarvis.speech.piper_rt import get_speaker

    speaker = get_speaker(VOICE)
    buffer = ""
    t0 = time.perf_counter()
    printed = ""
    first_frag_at = None

    # Flush as soon as we have a complete sentence OR ~22 chars of a
    # long first sentence, so the first audio starts right after TTFB.
    _FLUSH_RE = re.compile(r".*[.!?]\s*$", re.S)

    def _flush():
        nonlocal buffer
        if buffer.strip() and re.search(r"[a-zA-Z0-9]", buffer):
            speaker.feed(buffer)
        buffer = ""

    for frag in chat_stream_ollama(text):
        if frag is None:
            continue
        if first_frag_at is None:
            first_frag_at = time.perf_counter()
            print(f"[TIMING] LLM first content: {(first_frag_at - t0) * 1000:.0f} ms")
        printed += frag
        buffer += frag
        # Sentence boundary, OR a long fragment ending at a word boundary
        # (split only on whitespace so piper never receives half a word).
        if _FLUSH_RE.match(buffer) or (
            len(buffer) >= 22 and buffer.endswith((" ", "\n"))
        ):
            _flush()
    _flush()
    print(f"\nJARVIS: {printed}")


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
