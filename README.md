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

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Harshthesas3/JARVIS_V1.git
cd JARVIS_V1
```

Or download the ZIP directly:

1. Click the green **Code** button on GitHub.
2. Select **Download ZIP**.
3. Extract the ZIP file.
4. Open a terminal inside the extracted folder.

---

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it:

#### Windows

```bash
.venv\Scripts\activate
```

#### Linux / macOS

```bash
source .venv/bin/activate
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Install Ollama

Download Ollama:

https://ollama.com/download

Verify installation:

```bash
ollama --version
```

---

### 5. Download a Language Model

Example:

```bash
ollama pull qwen3:4b
```

You may substitute another Ollama-compatible model if desired.

---

### 6. Start Ollama

```bash
ollama serve
```

---

### 7. Run JARVIS

```bash
python jarvis_v2.py
```

(depending on your configured entry point)

---

### 8. Voice Setup

Ensure:

- Microphone access is enabled in Windows.
- Speech recognition dependencies are installed.
- Ollama is running before launching JARVIS.

---

### Troubleshooting

#### Ollama Connection Error

Verify:

```bash
ollama list
```

returns your installed model.

#### Microphone Not Detected

Check:

```text
Windows Settings → Privacy & Security → Microphone
```

and allow desktop apps to access the microphone.

#### Missing Python Packages

Run:

```bash
pip install -r requirements.txt
```

again to reinstall dependencies.

## Project Structure

```text
JARVIS_V1
│
├── LICENSE
├── README.md
├── app_launcher.py
├── app_profiles.py
├── TTS.py
├── calendar_manager.py
├── clipboard.py
├── config.py
├── context_engine.py
├── file_management.py
├── jarvis.py
├── planner.py
├── reminder.py
├── search.py
├── session_memory.py
├── speech_correction.py
├── task_executor.py
├── ui_core.py
├── voice_input.py
├── web_search.py
├── window_management.py
├── desktop_search.py
└── other supporting modules...
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
