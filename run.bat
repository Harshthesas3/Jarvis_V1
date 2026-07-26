@echo off
title JARVIS OS Launcher
echo Starting JARVIS OS...
call venv\Scripts\activate.bat
python -m jarvis.main %*
pause
