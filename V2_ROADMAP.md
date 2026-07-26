# JARVIS V2 Design Roadmap

## Vision
Transform JARVIS from a command-driven script into a proactive, context-aware OS agent. Transition from a "Request $\rightarrow$ Response" model to an "Observation $\rightarrow$ Reasoning $\rightarrow$ Action" loop, minimizing hardcoded paths and maximizing reliability across different Windows environments.

## Goals
1. **Environment Agnostic**: Remove all hardcoded user paths and implement a dynamic configuration system.
2. **Proactive Intelligence**: Implement a background "Observer" that can suggest actions based on screen state and active windows.
3. **Robust Memory**: Upgrade from a flat JSON list to a semantic memory system (vector-based) for better fact retrieval.
4. **Asynchronous Core**: Move to an async architecture to prevent TTS/ASR from blocking the main execution loop.
5. **Advanced Automation**: Expand the `search_agent` into a general-purpose UI automation framework.

## Architecture Evolution
- **From**: Linear Pipeline (Voice $\rightarrow$ Plan $\rightarrow$ Exec $\rightarrow$ Voice).
- **To**: Agentic Loop:
    - **Perception Layer**: Continuous monitoring of active windows, clipboard, and screen.
    - **Cognitive Layer**: LLM-driven reasoning that combines current intent with perceived context.
    - **Execution Layer**: Decoupled tool-set with built-in validation and automatic retry logic.
    - **Interface Layer**: Non-blocking async TTS and ASR.

## Milestones

### Milestone 1: Foundation & Configuration
- **Goal**: Decouple the system from the local environment.
- **Tasks**:
    - Implement `config.json` for paths (Piper, Models, Voice).
    - Create a `SettingsManager` class for runtime configuration.
    - Standardize logging and error reporting.
- **Priority**: Critical
- **Complexity**: Low
- **Test**: Verify JARVIS starts on a different machine by only changing `config.json`.

### Milestone 2: Asynchronous Core & TTS/ASR
- **Goal**: Eliminate UI/Voice blocking.
- **Tasks**:
    - Convert `main` loop to `asyncio`.
    - Move `speak()` to a background worker queue.
    - Implement non-blocking audio recording and transcription.
- **Priority**: High
- **Complexity**: Medium
- **Test**: Trigger a long TTS response and verify the assistant can still listen for a "stop" command.

### Milestone 3: Semantic Memory Upgrade
- **Goal**: Move beyond simple string matching for facts.
- **Tasks**:
    - Integrate a lightweight local vector store (e.g., ChromaDB or FAISS).
    - Implement "Memory Consolidation" (summarizing old facts).
    - Enable context-aware recall based on current activity.
- **Priority**: Medium
- **Complexity**: High
- **Test**: Store 50 diverse facts and verify retrieval of a specific fact using a paraphrased query.

### Milestone 4: Proactive Observer (Vision Loop)
- **Goal**: Give JARVIS "eyes" that work without being asked.
- **Tasks**:
    - Implement a background thread that snapshots the screen every $N$ seconds.
    - Use a lightweight vision model to detect "Error" states or "Loading" screens.
    - Create a `ProactiveTrigger` system to interrupt the user with helpful suggestions.
- **Priority**: Medium
- **Complexity**: High
- **Test**: Open a terminal with a visible error and verify JARVIS offers to help without a prompt.

### Milestone 5: Universal UI Automator
- **Goal**: Generalize `search_agent` for any app.
- **Tasks**:
    - Create a generic `ElementAction` map (Find $\rightarrow$ Interact $\rightarrow$ Verify).
    - Implement a "UI Recorder" to allow the user to teach JARVIS new app workflows.
    - Expand `StrictWindowValidator` to support all common Windows process types.
- **Priority**: Medium
- **Complexity**: High
- **Test**: Successfully automate a 3-step process in a previously unsupported application.

## Dependencies
- **Language**: Python 3.12+
- **LLM/Vision**: Ollama (Qwen 2.5 / Qwen2.5VL)
- **UI**: Pywinauto, PyAutoGUI, mss, pycaw
- **Audio**: Faster-Whisper, Piper, SoundDevice
- **Storage**: JSON (Current), ChromaDB/FAISS (Proposed)

## Risk Analysis
| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **LLM Hallucinations** | High | Strict JSON validation and "Human-in-the-loop" confirmation for destructive actions. |
| **CPU Bottleneck** | Medium | Offload ASR/TTS to dedicated threads; optimize Whisper model size. |
| **OS Updates** | Medium | Use a combination of Win32 API and Accessibility IDs to ensure fallback reliability. |
| **Privacy Concerns** | High | Ensure all vision/audio processing remains 100% local (no cloud API calls). |
