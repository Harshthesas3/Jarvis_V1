@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python jarvis_v2.py
if errorlevel 1 pause
