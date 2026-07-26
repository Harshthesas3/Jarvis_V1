# Voice Subsystem Architecture

## Overview

JARVIS features a continuous, low-latency Voice-First interaction loop:

```
[PASSIVE MODE]
  ├── Continuous mic stream (tiny Whisper model)
  └── Listens for wake words: "I'm back", "Hey Jarvis"
       │
       ▼ (Wake Detected -> Play Confirmation)
[ACTIVE MODE]
  ├── Continuous mic stream (base Whisper model)
  ├── FastCommandRouter pre-filter (<2ms)
  └── LLM Planner fallback for complex requests
       │
       ▼ (Dismissal phrase heard: "goodbye", "sleep")
[PASSIVE MODE]
```

## Speech-to-Text (STT)

- **Engine**: Quantized `faster-whisper` (`int8` compute on CPU/GPU).
- **Wake Word Detection**: Runs a background 2-second sliding window buffer.
- **VAD (Voice Activity Detection)**: Energy thresholding automatically detects speech pauses (1.5s silence trigger).

## Text-to-Speech (TTS)

- **Engine**: Piper neural TTS with ONNX runtime.
- **Playback Safety**: Thread-safe lock protects audio output buffers (`sounddevice`), with event waiters blocking until speech playback completes cleanly.
