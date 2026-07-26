# Configuration Guide

## Configuration File: `config.json`

JARVIS reads configuration from `config.json` in the root directory. If the file is missing or corrupted, sensible defaults are used.

### Full Schema

```json
{
  "paths": {
    "piper_exe": "C:\\path\\to\\piper.exe",
    "voice_model": "C:\\path\\to\\voice.onnx",
    "screenshot_dir": "Screenshots"
  },
  "models": {
    "chat_model": "qwen3.5:4b",
    "planner_model": "qwen3.5:4b",
    "vision_model": "qwen2.5vl:3b"
  },
  "voice": {
    "wake_phrases": ["i'm back", "i am back", "im back"],
    "chat_history_limit": 10
  },
  "system": {
    "system_prompt": "You are JARVIS..."
  }
}
```

## Configuration Sections

### `paths` — File System Paths

| Key | Default | Description |
|-----|---------|-------------|
| `piper_exe` | `"piper.exe"` | Path to the Piper TTS executable |
| `voice_model` | `"voice.onnx"` | Path to the Piper voice model (.onnx) |
| `screenshot_dir` | `"Screenshots"` | Directory for captured screenshots |

**Note:** On first setup, these paths must point to your actual Piper installation. The defaults will not work without configuration.

### `models` — Ollama Model Names

| Key | Default | Description |
|-----|---------|-------------|
| `chat_model` | `"qwen3.5:4b"` | Model for conversational chat fallback |
| `planner_model` | `"qwen3.5:4b"` | Model for LLM-based intent planning |
| `vision_model` | `"qwen2.5vl:3b"` | Model for vision-based screen analysis |

All models must be pulled into Ollama before use:
```bash
ollama pull qwen3.5:4b
ollama pull qwen2.5vl:3b
```

### `voice` — Voice/Audio Settings

| Key | Default | Description |
|-----|---------|-------------|
| `wake_phrases` | `["i'm back"]` | List of phrases that activate the assistant |
| `chat_history_limit` | `10` | Number of recent turns to include in chat context |

### `system` — System Behavior

| Key | Default | Description |
|-----|---------|-------------|
| `system_prompt` | `"You are JARVIS."` | Base system prompt for the LLM |

The system prompt is augmented with remembered facts from memory before each chat call.

## Defaults

If a config key is missing, `SettingsManager` provides these defaults:

```python
{
    "paths": {
        "piper_exe": "piper.exe",
        "voice_model": "voice.onnx",
        "screenshot_dir": "Screenshots"
    },
    "models": {
        "chat_model": "qwen3.5:4b",
        "planner_model": "qwen3.5:4b",
        "vision_model": "qwen2.5vl:3b"
    },
    "voice": {
        "wake_phrases": ["i'm back"],
        "chat_history_limit": 10
    },
    "system": {
        "system_prompt": "You are JARVIS."
    }
}
```

## Programmatic Access

```python
from settings_manager import settings

# Get a value with dot notation
piper_path = settings.get("paths.piper_exe")
model_name = settings.get("models.chat_model")
prompt = settings.get("system.system_prompt")

# With default fallback
timeout = settings.get("voice.timeout", 5.0)

# Reload from disk
settings.reload()
```

## Configuration Files Overview

| File | Purpose | Auto-Created | Managed By |
|------|---------|-------------|------------|
| `config.json` | User configuration | No (manual) | `SettingsManager` |
| `apps.json` | Installed applications cache | Yes | `generate_apps.py` / `app_launcher.py` |
| `memory.json` | Legacy fact storage | Yes | `memory.py` / `memory_v2.py` |
| `reminders.json` | Reminder storage | Yes | `reminders.py` |
| `disabled_plugins.json` | Plugin disabled state | Yes | `PluginManager` |

## Environment Variables

No environment variables are required. All configuration is file-based.

## Tips

- **Paths**: Use double backslashes (`\\`) or forward slashes (`/`) in JSON paths on Windows
- **UTF-16**: `config.json` and `apps.json` are read with multiple encoding attempts (UTF-16, UTF-8-BOM, UTF-8) for robustness
- **Memory**: `memory_v2.py` stores facts in `memory.json` (backward compat) and creates automatic backups in `Backups/`
- **Reminders**: Stored in `reminders.json` with ISO 8601 datetime strings
- **Plugins**: Disabled plugins are tracked in `disabled_plugins.json`; remove entries from this file to re-enable
