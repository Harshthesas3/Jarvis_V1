# JARVIS Configuration Guide

JARVIS reads configuration from environment variables defined in `.env` or settings in `config.yaml`.

## Environment Variables (`.env`)

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `JARVIS_ENV` | `production` | Environment mode (`development` / `production`). |
| `JARVIS_HOST` | `127.0.0.1` | REST API server listen address. |
| `JARVIS_PORT` | `8000` | REST API server port. |
| `JARVIS_CHAT_MODEL` | `qwen3.5:4b` | Ollama model name used for general chat & planning. |
| `JARVIS_VISION_MODEL` | `qwen2.5vl:3b` | Ollama vision model name used for screen awareness. |
| `JARVIS_STT_WAKE_MODEL` | `tiny` | Faster-Whisper model used for passive wake-word detection. |
| `JARVIS_STT_CMD_MODEL` | `base` | Faster-Whisper model used for active command transcription. |
| `JARVIS_PIPER_EXE` | `""` | Absolute path to Piper TTS executable (optional). |
| `JARVIS_VOICE_MODEL` | `""` | Absolute path to Piper `.onnx` voice model (optional). |

## File Configuration (`config.yaml`)

You can also customize paths, models, and voice settings via `config.yaml`:

```yaml
system:
  env: production
  host: "127.0.0.1"
  port: 8000

models:
  chat_model: "qwen3.5:4b"

voice:
  wake_phrases:
    - "i'm back"
    - "hey jarvis"
    - "jarvis"
```
