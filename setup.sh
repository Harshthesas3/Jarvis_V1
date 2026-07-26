#!/usr/bin/env bash
# JARVIS OS Automated Setup Script for Linux/macOS

set -e

echo "============================================================"
echo "          JARVIS OS 3.0 — Automated Setup Script"
echo "============================================================"
echo ""

# 1. Verify Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed!"
    exit 1
fi
echo "[OK] Python 3 detected: $(python3 --version)"

# 2. Virtual Environment
if [ ! -d "venv" ]; then
    echo "[INFO] Creating virtual environment..."
    python3 -m venv venv
fi
echo "[OK] Virtual environment ready."

# 3. Install Dependencies
echo "[INFO] Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt || echo "[WARNING] Some dependencies had warnings."

# 4. Environment configuration
if [ ! -f ".env" ]; then
    echo "[INFO] Creating .env from template..."
    cp .env.example .env
fi

# 5. Directories
mkdir -p Screenshots CalendarEvents Backups

# 6. Verify Ollama
if ! command -v ollama &> /dev/null; then
    echo "[WARNING] Ollama not found. Install from https://ollama.com for full LLM features."
else
    echo "[OK] Ollama detected."
fi

echo ""
echo "============================================================"
echo "[SUCCESS] JARVIS setup complete!"
echo "Run './run.sh' to start JARVIS."
echo "============================================================"
