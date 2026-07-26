@echo off
title JARVIS OS Launcher
cd /d "%~dp0"
set PYTHONPATH=src;%PYTHONPATH%
echo Starting JARVIS OS...
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
python -m jarvis.main %*
pause
