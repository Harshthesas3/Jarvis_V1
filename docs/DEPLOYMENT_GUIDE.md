# Deployment Guide

## System Requirements

### Minimum
- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.12+
- **RAM**: 8 GB
- **CPU**: 4 cores (x86-64 with AVX2 support)
- **Storage**: 10 GB free (for models)
- **Microphone**: Working input device

### Recommended
- **RAM**: 16 GB
- **CPU**: 8 cores (Intel i7 / AMD Ryzen 7 or better)
- **Storage**: SSD, 20 GB free
- **GPU**: NVIDIA GPU with 4+ GB VRAM (optional, for faster Whisper)

## Installation

### 1. Python Setup

```powershell
# Install Python 3.12 from python.org (ensure "Add to PATH")

# Verify
python --version  # Must be 3.12+
pip --version
```

### 2. Clone and Virtual Environment

```powershell
git clone <repository-url> Jarvis
cd Jarvis
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

**If `requirements.txt` is missing**, install manually:

```powershell
pip install ollama faster-whisper sounddevice scipy pyautogui pywinauto keyboard psutil pycaw comtypes mss pytesseract Pillow
```

Optional (for memory v2 semantic search):
```powershell
pip install faiss-cpu sentence-transformers
```

### 4. Install Ollama

```powershell
# Download from https://ollama.com/download
# Run the installer

# Verify
ollama --version

# Pull required models
ollama pull qwen3.5:4b
ollama pull qwen2.5vl:3b
```

**Note**: First pull may take several minutes depending on download speed.

### 5. Install Piper TTS

```powershell
# Download piper.exe from https://github.com/rhasspy/piper/releases
# Download a voice model (e.g., en_US-lessac-medium.onnx) from:
# https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium

# Place both files in a known location
# Update config.json with the paths
```

### 6. Configure

```powershell
# Edit config.json with your paths
notepad config.json
```

Example `config.json`:
```json
{
  "paths": {
    "piper_exe": "C:\\Tools\\piper.exe",
    "voice_model": "C:\\Tools\\en_US-lessac-medium.onnx",
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
    "system_prompt": "You are JARVIS. You are Harshith's personal AI assistant. Always address Harshith as sir. Keep answers concise. Never use emojis. Never use markdown. Speak naturally and professionally."
  }
}
```

### 7. Generate App Cache (Optional)

```powershell
python generate_apps.py
# This creates apps.json with all installed Windows applications
```

### 8. Verify Installation

```powershell
# Run diagnostics
python -c "from diagnostics import check_environment, print_report; print_report(check_environment())"
```

Expected output should show `[OK]` for most components.

## Running

### Production Mode

```powershell
.\venv\Scripts\Activate.ps1
python jarvis_v2.py
```

The assistant will:
1. Print startup diagnostics
2. Load Whisper models (this takes ~10-20 seconds)
3. Display "JARVIS READY"
4. Wait for wake phrase "I'm back"

### Auto-Start (Windows)

Create a PowerShell script `start_jarvis.ps1`:

```powershell
Set-Location -LiteralPath "C:\Jarvis"
.\venv\Scripts\Activate.ps1
python jarvis_v2.py
```

Add to Task Scheduler or Startup folder:
- Press `Win+R`, type `shell:startup`
- Create a shortcut to the script or to `powershell.exe -File "C:\Jarvis\start_jarvis.ps1"`

### Headless / Debug Mode

```powershell
# Text-only mode (no voice)
python jarvis.py
```

## Performance Tuning

### Faster Whisper Models

| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| `tiny` | 39 MB | Fastest | Low | Wake word only |
| `base` | 74 MB | Fast | Medium | Command capture |
| `small` | 244 MB | Moderate | Good | Better accuracy |
| `medium` | 769 MB | Slow | Better | High accuracy |
| `large-v3` | ~3 GB | Slowest | Best | Maximum accuracy |

Modify model sizes in `jarvis_v2.py`:
```python
wake = WhisperModel("tiny", ...)     # Wake word
command = WhisperModel("base", ...)  # Commands
```

### Ollama Models

| Model | Size | Quality | Hardware |
|-------|------|---------|----------|
| `qwen3.5:4b` | ~2.5 GB | Good | 8 GB RAM |
| `qwen2.5:7b` | ~4.5 GB | Better | 16 GB RAM |
| `qwen2.5vl:3b` | ~2 GB (vision) | Good | 8 GB RAM |

### GPU Acceleration

Whisper can use GPU with CUDA:
```powershell
pip install faster-whisper[cuda]
```

Then modify the device parameter:
```python
wake = WhisperModel("tiny", device="cuda", compute_type="float16")
command = WhisperModel("base", device="cuda", compute_type="float16")
```

## Production Checklist

- [ ] All paths in `config.json` are correct and absolute
- [ ] Ollama is running as a service (not manually launched)
- [ ] Piper TTS binary and voice model are accessible
- [ ] Microphone is configured as default input device
- [ ] Speaker/headphones are connected and working
- [ ] `apps.json` has been generated
- [ ] Startup diagnostics pass
- [ ] Virtual environment is activated
- [ ] JARVIS added to startup (optional)

## Troubleshooting

### Common Issues

**"Ollama is not running"**
- Ensure Ollama is installed and the service is running
- Run `ollama serve` in a terminal
- Check that models are pulled: `ollama list`

**"Piper executable not found"**
- Verify the path in `config.json` → `paths.piper_exe`
- Ensure the path uses double backslashes (`\\`)
- Test manually: `& "C:\path\to\piper.exe" --help`

**"No microphone detected"**
- Check Windows microphone settings
- Ensure no other app is using the microphone
- Test with: `python -c "import sounddevice; print(sounddevice.query_devices())"`

**"Whisper model loading failed"**
- Ensure enough RAM is available
- Try a smaller model (tiny instead of base)
- Check disk space for model cache

**"No response from assistant"**
- Check the console output for errors
- Verify wake word detection prints "Heard: ..."
- Test TTS independently: `python -c "from jarvis_v2 import speak; speak('test')"`

**"Application not found"**
- Run `python generate_apps.py` to refresh the app cache
- Try the full application name instead of an alias
- Check `apps.json` exists and has entries

### Logs

Logs are printed to stdout. To capture:

```powershell
python jarvis_v2.py > jarvis.log 2>&1
```

Critical errors are logged with `ERROR` level. Warning-level events indicate recoverable issues.

## Backup and Recovery

### Memory Backups

`memory_v2.py` automatically creates backups in `Backups/` every 5 minutes. To restore:

```python
from memory_v2 import get_memory
memory = get_memory()
memory.load_backup("Backups/memory_backup_1234567890.json")
```

### Reminders

Reminders are stored in `reminders.json`. Backup this file periodically.

### Configuration

Backup `config.json` as your primary configuration. Store it alongside the project or in version control (with personal paths redacted).

## Updating

```powershell
git pull
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt --upgrade
```

Check `V2_ROADMAP.md` for breaking changes between versions.
