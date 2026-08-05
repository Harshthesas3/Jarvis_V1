"""Latency benchmark harness for the JARVIS voice pipeline.

Measures each stage of the pipeline independently so optimizations can be
verified with before/after numbers:

    python latency_bench.py [--stt] [--tts] [--llm] [--planner] [--startup] [--all]
"""

import argparse
import io
import json
import os
import subprocess
import sys
import time
import wave
from statistics import mean, median

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

SAMPLE_TEXT = "Good morning sir, what time is it"
TTS_TEXT = "Systems online sir, awaiting instructions"

RESULTS = {}


def bench(name, fn, runs=3, warmup=0):
    times = []
    for _ in range(warmup):
        fn()
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    m = median(times)
    RESULTS[name] = {"ms": round(m, 1), "runs": [round(t, 1) for t in times]}
    print(f"  {name:55s} median {m:8.1f} ms   runs={[round(t,1) for t in times]}")
    return m


def make_speech_sample(piper_exe, voice_model):
    """Synthesize a short speech sample via piper to feed STT benchmarks."""
    wav = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bench_sample.wav")
    if os.path.exists(wav):
        return wav
    subprocess.run(
        [piper_exe, "-m", voice_model, "-f", wav],
        input=SAMPLE_TEXT, text=True, capture_output=True, timeout=60,
    )
    return wav


def bench_stt(sample_wav):
    import numpy as np
    from faster_whisper import WhisperModel

    data, fs = None, 16000
    try:
        import soundfile as sf
        data, fs = sf.read(sample_wav)
        data = data.astype(np.float32)
    except Exception:
        from scipy.io import wavfile
        fs, data = wavfile.read(sample_wav)
        data = (data / 32768.0).astype(np.float32)

    for model_name, device in (("tiny", "cpu"), ("tiny", "cuda"), ("base", "cpu"), ("base", "cuda")):
        try:
            t0 = time.perf_counter()
            model = WhisperModel(model_name, device=device, compute_type="int8")
            load_ms = (time.perf_counter() - t0) * 1000.0
            print(f"  load whisper {model_name}/{device:4s}        {load_ms:8.1f} ms")

            def trans():
                segs, _ = model.transcribe(data, language="en")
                return " ".join(s.text for s in segs)
            t = bench(f"STT {model_name}/{device}", trans, runs=3, warmup=1)
            print(f"      -> transcript: {trans()!r}")
        except Exception as exc:
            print(f"  STT {model_name}/{device}: FAILED {exc}")


def bench_tts(piper_exe, voice_model):
    wav = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bench_tts.wav")

    def subprocess_tts():
        subprocess.run(
            [piper_exe, "-m", voice_model, "-f", wav],
            input=TTS_TEXT, text=True, capture_output=True, timeout=30,
        )
    bench("TTS subprocess (spawn+synth)", subprocess_tts, runs=3, warmup=1)

    try:
        import numpy as np
        from piper import PiperVoice

        t0 = time.perf_counter()
        voice = PiperVoice.load(voice_model)
        load_ms = (time.perf_counter() - t0) * 1000.0
        print(f"  load piper in-process voice        {load_ms:8.1f} ms")

        def inproc_tts():
            wav_data = io.BytesIO()
            with wave.open(wav_data, "wb") as wf:
                voice.synthesize_wav(TTS_TEXT, wf)
        bench("TTS in-process (synth only)", inproc_tts, runs=3, warmup=1)
    except Exception as exc:
        print(f"  TTS in-process: FAILED {exc}")


def bench_llm():
    try:
        import ollama
        client = ollama.Client()

        def first_token(model):
            t0 = time.perf_counter()
            stream = client.chat(
                model=model,
                messages=[{"role": "user", "content": "Say yes in one word."}],
                options={"num_predict": 8},
                stream=True,
            )
            first = None
            for chunk in stream:
                if chunk.get("message", {}).get("content"):
                    first = time.perf_counter()
                    break
            ttft = (first - t0) * 1000.0 if first else None
            return ttft

        for model in ("qwen3.5:4b", "qwen3.5:2b", "qwen3.5:0.8b", "qwen3:0.6b"):
            try:
                ttft = first_token(model)
                if ttft is not None:
                    print(f"  LLM {model:14s} first-token(warm)  {ttft:8.1f} ms")
            except Exception as exc:
                print(f"  LLM {model}: FAILED {exc}")
    except Exception as exc:
        print(f"  LLM bench failed: {exc}")


def bench_planner():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fast_router import FastCommandRouter
    from settings_manager import settings
    from jarvis.fast_command_router import get_fast_router

    ctx = {"speak": print, "settings": settings}
    router = FastCommandRouter(ctx)
    jrouter = get_fast_router()

    bench("legacy fast_router 'what time is it'", lambda: router.route("what time is it"), runs=5)
    bench("jarvis fast_router 'open chrome'", lambda: jrouter.route("open chrome"), runs=5)

    import planner
    bench("planner._try_fast_path 'open chrome'", lambda: planner._try_fast_path("open chrome"), runs=5)
    bench("planner.plan_action(use_llm=False) 'open chrome'",
          lambda: planner.plan_action("open chrome", use_llm=False), runs=5)

    t0 = time.perf_counter()
    mem = None
    try:
        from memory_v2 import get_memory
        mem = get_memory()
        load_ms = (time.perf_counter() - t0) * 1000.0
        print(f"  memory_v2.get_memory() load          {load_ms:8.1f} ms")
    except Exception as exc:
        print(f"  memory_v2 load failed: {exc}")


def bench_startup():
    t0 = time.perf_counter()
    import jarvis_v2 as _  # noqa: F401
    elapsed = (time.perf_counter() - t0) * 1000.0
    print(f"  import jarvis_v2 (full startup path) {elapsed:8.1f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stt", action="store_true")
    ap.add_argument("--tts", action="store_true")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--planner", action="store_true")
    ap.add_argument("--startup", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    cfg = json.load(open("config.json", encoding="utf-8"))
    piper_exe = cfg["paths"]["piper_exe"]
    voice_model = cfg["paths"]["voice_model"]

    do_all = args.all or not any((args.stt, args.tts, args.llm, args.planner, args.startup))

    print(f"== JARVIS latency benchmark @ {time.strftime('%H:%M:%S')} ==")
    print(f"piper: {piper_exe}\nvoice: {voice_model}")

    if do_all or args.stt:
        print("\n-- STT (faster-whisper) --")
        sample = make_speech_sample(piper_exe, voice_model)
        bench_stt(sample)

    if do_all or args.tts:
        print("\n-- TTS (piper) --")
        bench_tts(piper_exe, voice_model)

    if do_all or args.llm:
        print("\n-- LLM (ollama) --")
        bench_llm()

    if do_all or args.planner:
        print("\n-- Planner / router / memory --")
        bench_planner()

    if args.startup:
        print("\n-- Startup (import jarvis_v2) --")
        bench_startup()

    print("\n== SUMMARY ==")
    for name, r in RESULTS.items():
        print(f"  {name:45s} {r['ms']:8.1f} ms")


if __name__ == "__main__":
    main()
