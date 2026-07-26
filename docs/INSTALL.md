# JARVIS Installation Guide

This document provides step-by-step instructions for installing and running JARVIS on Windows, Linux, and macOS.

## Prerequisites

1. **Python 3.10+**: Ensure Python is installed and added to system `PATH`.
2. **Ollama (Optional but Recommended)**: Required for conversational reasoning and complex planning. Download from [ollama.com](https://ollama.com).
   - Recommended models: `ollama pull qwen3.5:4b` and `ollama pull qwen2.5vl:3b`
3. **FFmpeg (Optional)**: Required for specific audio format conversions.

## Quick Automated Setup

### Windows
```cmd
git clone https://github.com/your-username/jarvis.git
cd jarvis
setup.bat
```

### Linux / macOS
```bash
git clone https://github.com/your-username/jarvis.git
cd jarvis
chmod +x setup.sh
./setup.sh
```

## Manual Setup

If you prefer to configure the environment manually:

1. **Create Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment**:
   ```bash
   cp .env.example .env
   ```
4. **Run Preflight Verification**:
   ```bash
   python -m jarvis.main --health
   ```
5. **Start JARVIS**:
   ```bash
   python -m jarvis.main
   ```
