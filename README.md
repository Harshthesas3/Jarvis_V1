# JARVIS_V1

JARVIS is a voice-controlled AI desktop assistant for Windows that combines natural language understanding, intelligent task planning, and desktop automation. It enables users to control applications, manage files, perform searches, and execute complex multi-step workflows using voice or text commands.

## Features

### Voice Interaction

* Wake-word activation
* Speech-to-text command recognition
* Natural language understanding
* Text-to-speech responses

### Desktop Automation

* Launch and control desktop applications
* Intelligent window detection and focus management
* Universal in-app search automation
* Keyboard and mouse control
* Multi-step workflow execution

### File Management

* Create, open, rename, and delete files
* Create and manage folders
* Read and write file contents
* Clipboard operations

### Productivity

* Reminders and scheduled tasks
* Web search integration
* Context-aware command execution
* Session memory for follow-up commands

## Example Commands

```text
Open Microsoft Store and search for Spotify

Open Apple Music and search for Thriller

Create a folder called Python Projects

Create a file called test.py and write a Hello World program

Open Downloads, create a folder called JarvisTests, create a file called notes.txt, write hello world, and read it back to me

Remind me in 10 minutes to submit my assignment
```

## Architecture

JARVIS uses a hybrid architecture consisting of:

* Speech Recognition Layer
* Natural Language Planning Engine
* Deterministic Task Executor
* Desktop Automation Engine
* Window and Process Management
* Application Search Framework
* Memory and Context Management

The assistant converts natural language into structured execution plans and validates each step before proceeding to the next action.

## Technology Stack

* Python
* Faster-Whisper
* Ollama
* PyAutoGUI
* PyWinAuto
* Pytesseract
* MSS
* PSUtil
* Windows UI Automation

## Project Structure

```text
JARVIS
├── jarvis_v2.py
├── planner.py
├── task_executor.py
├── ui_core.py
├── context_engine.py
├── session_memory.py
├── speech_correction.py
└── app_profiles/
```

## Design Goals

* Reliable desktop automation
* Natural language interaction
* Deterministic task execution
* Extensible architecture
* Local-first operation
* Fast response times
* Production-grade reliability

## Future Roadmap

* Visual desktop understanding
* OCR-driven automation
* Browser automation
* Agentic workflow execution
* Cross-platform support
* Advanced memory and personalization
* Multi-agent task orchestration

## License

This project is intended for educational, research, and productivity purposes. Please review the license before use.

## Author

T Harshith Krishna Sastry

RV College of Engineering (RVCE)

Electronics and Communication Engineering
