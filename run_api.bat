@echo off
title JARVIS API Server Launcher
echo Starting JARVIS REST API Server on port 8000...
call venv\Scripts\activate.bat
python -m jarvis.main --api --port 8000
pause
