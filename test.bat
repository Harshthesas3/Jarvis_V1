@echo off
title JARVIS Test Suite Runner
echo Running JARVIS Unit Test Suite...
call venv\Scripts\activate.bat
python -m unittest discover -s tests -p "test_*.py"
pause
