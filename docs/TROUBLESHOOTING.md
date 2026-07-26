# Troubleshooting Guide

Common issues and resolution steps for JARVIS OS.

## 1. Microphone Not Detected or Speech Recognition Fails
- **Symptoms**: `sounddevice` error or silent logs during voice capture.
- **Resolution**:
  1. Ensure your default input device is connected and set properly in Windows Sound Settings.
  2. Verify PyAudio / sounddevice installation: `pip install PyAudio sounddevice`.

## 2. Ollama Connection Error / Fallback Mode
- **Symptoms**: Logs report `LLM circuit breaker is open` or `having trouble reaching the language model`.
- **Resolution**:
  1. Verify Ollama is running locally: `ollama list`.
  2. Start Ollama service: `ollama serve`.
  3. Ensure the configured chat model is pulled: `ollama pull qwen3.5:4b`.

## 3. TTS Audio Cut Off
- **Symptoms**: Speech stops before completing a sentence.
- **Resolution**:
  - The thread synchronization fix in v3.0 ensures `wait_for_playback()` is called. If using custom TTS backends, verify your output device buffer size.

## 4. Application Not Launching
- **Symptoms**: Voice command says "App not found".
- **Resolution**:
  - JARVIS scans Start Menu, Desktop, and PATH executables into `apps.json`.
  - Rebuild the application index by running: `python -c "from jarvis.windows_discovery import ApplicationResolver; ApplicationResolver()._initial_load()"`.
