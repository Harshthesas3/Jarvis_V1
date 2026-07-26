# JARVIS Architecture Guide (v3.0.0)

## System Architecture

JARVIS is architected as an **AI Operating System for Windows** with clean layered separation. Every layer communicates through formal interfaces (ABCs) registered in a dependency injection container and coordinated through an event bus.

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                              │
│  main.py (CLI) │──headless──│──voice──│──health──│──api (future)──│    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                          VOICE LAYER                                    │
│  ASREngine ← FasterWhisper    │    TTSEngine ← Piper                   │
│  WakeWordEngine ← WhisperTiny │    Speech → Text → Intent              │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                          INTENT LAYER                                   │
│  IntentClassifier ────→ IntentResult                                    │
│    • LLM-based intent classification                                   │
│    • Confidence scoring                                                 │
│    • Capability resolution                                              │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                          PLANNER LAYER                                  │
│  Planner ─────────────→ ExecutionGraph (DAG)                           │
│    • Regex fast-path (deterministic, no LLM)                           │
│    • LLM decomposition for multi-step                                  │
│    • Capability handlers (domain-specific)                              │
│    • Pronunciation resolution / context injection                      │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                       EXECUTION GRAPH LAYER                             │
│  ExecutionGraph ─── Contains ───→ TaskNode[] (DAG)                     │
│    • Topological ordering                                               │
│    • Dependency resolution                                              │
│    • Cycle detection                                                    │
│    • Validation                                                         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                       EXECUTION ENGINE                                  │
│  GraphExecutionEngine                                                   │
│    • Dependency-aware scheduling                                        │
│    • Retry with exponential backoff                                     │
│    • Per-task timeout enforcement                                       │
│    • Cancellation support                                               │
│    • Progress callbacks / event bus integration                         │
│    • Execution tracking + metrics                                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                          ADAPTERS LAYER                                 │
│  TaskHandler implementations                                           │
│    • LegacyHandlerAdapter (wraps existing task_executor handlers)       │
│    • Native handlers (migrated to new architecture)                     │
│                                                                         │
│  Concrete Adapters:                                                     │
│    ┌─────────────┐ ┌─────────────┐ ┌──────────────┐ ┌───────────────┐  │
│    │ AppLauncher │ │ UIAutomator │ │ SearchAgent  │ │ ScreenCapture │  │
│    └─────────────┘ └─────────────┘ └──────────────┘ └───────────────┘  │
│    ┌─────────────┐ ┌─────────────┐ ┌──────────────┐ ┌───────────────┐  │
│    │ FileManager │ │ Reminders   │ │ Calendar     │ │ CodeGenerator │  │
│    └─────────────┘ └─────────────┘ └──────────────┘ └───────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                     OPERATING SYSTEM LAYER                              │
│  Win32 API │ PyWinAuto │ PyAutoGUI │ PowerShell │ MSS │ Ollama         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Package Structure

```
src/jarvis/
├── __init__.py              # Package root + version
├── _version.py              # Version info (3.0.0)
├── types.py                 # Core shared types (no layer dependencies)
├── app.py                   # Application bootstrap + DI wiring
├── main.py                  # CLI entry point
│
├── interfaces/              # ★ Abstract interfaces (contracts)
│   ├── __init__.py
│   ├── speech.py            # ASREngine, WakeWordEngine, TTSEngine
│   ├── planner.py           # IntentClassifier, Planner, CapabilityHandler
│   ├── executor.py          # TaskHandler, ExecutionEngine, ExecutorContext
│   ├── memory.py            # MemoryStore, SemanticMemory, ConversationMemory
│   ├── automation.py        # WindowManager, UIElement, AppLauncher, SearchInApp
│   ├── vision.py            # ScreenCapture, VisionAnalyzer
│   ├── plugin.py            # PluginHost, Plugin
│   └── events.py            # EventBus, EventSubscriber, SystemEvent
│
├── di/                      # ★ Dependency Injection
│   ├── __init__.py
│   └── container.py         # ServiceContainer (thread-safe, parent scopes)
│
├── eventbus/                # ★ Event-Driven Communication
│   ├── __init__.py
│   ├── bus.py               # InMemoryEventBus (priority-ordered, async)
│   └── events.py            # Canonical event type constants
│
├── execution/               # ★ Execution Graph Engine
│   ├── __init__.py
│   ├── engine.py            # GraphExecutionEngine (DAG scheduler)
│   ├── task.py              # TaskBuilder, GraphBuilder (fluent APIs)
│   ├── tracker.py           # ExecutionTracker (metrics + history)
│   ├── scheduler.py         # TaskScheduler (delayed + recurring)
│   └── adapter.py           # LegacyHandlerAdapter + handler registry
│
├── services/                # Service implementations
│   ├── __init__.py
│   ├── config.py            # ConfigService (dot-notation, JSON persistence)
│   └── logging.py           # LoggingService (centralized config)
│
├── planner/                 # Intent planning (future — migrated from planner.py)
├── speech/                  # Speech implementations (future)
├── memory/                  # Memory implementations (future)
├── automation/              # Automation implementations (future)
├── plugins/                 # Plugin host (future)
├── api/                     # REST API (future)
├── voice/                   # Voice implementation (future)
└── vad/                     # Voice activity detection (future)
```

## Core Architectural Patterns

### 1. Dependency Injection

All services are registered in a `ServiceContainer` that supports:
- **Singleton services** — Same instance on every resolve (default)
- **Transient services** — New instance per resolve
- **Lazy initialization** — Created only when first resolved
- **Eager initialization** — Created at registration time
- **Hierarchical scopes** — Child containers fall back to parent
- **Lifecycle hooks** — `on_init()` called on first resolve

### 2. Event-Driven Communication

All layers communicate through an `EventBus` that supports:
- **Typed events** — `SystemEvent(type, source, data, priority)`
- **Priority ordering** — CRITICAL > HIGH > NORMAL > LOW
- **Synchronous publish** — Blocks until all handlers complete
- **Async publish** — Dispatches in daemon threads
- **Global subscribers** — Receive ALL events
- **Auto-subscription** — `EventSubscriber.get_subscriptions()`

### 3. Execution Graph (DAG)

All plans are transformed into directed acyclic graphs of `TaskNode`:
- **Deterministic ordering** — Topological sort with dependency resolution
- **Parallel support** — Nodes without dependencies can execute in parallel
- **Retry with backoff** — Exponential backoff (500ms, 1s, 2s, 4s, max 5s)
- **Per-task timeout** — Thread-based timeout enforcement
- **Cancellation** — Per-graph cancel flag with `threading.Event`
- **Observability** — Progress callbacks + event bus integration
- **Validation** — Cycle detection before execution

### 4. Adapter Pattern

The `LegacyHandlerAdapter` wraps existing handler functions from `task_executor.py`
as `TaskHandler` instances. This enables:
- **Gradual migration** — Existing handlers work in the new engine
- **Zero downtime** — No need to rewrite all handlers at once
- **Incremental improvement** — Handlers can be migrated one at a time

## Data Flow

```
User Speaks
    ↓
Wake Word Detection (Whisper Tiny)
    ↓
Command Capture (Whisper Base)
    ↓
Transcription Text
    ↓
Event: COMMAND_RECEIVED
    ↓
Planner.plan() ──→ Classification → Regex Fast-Path → LLM
    ↓                                                      ↓
Event: PLANNING_COMPLETE                            Multi-step DAG
    ↓
ExecutionGraph (validated DAG)
    ↓
Event: EXECUTION_STARTED
    ↓
GraphExecutionEngine.execute()
    ├── Topological sort
    ├── For each ready task:
    │   ├── Check dependencies met
    │   ├── Execute with timeout
    │   ├── Retry on failure (if configured)
    │   └── Emit task events
    └── Collect results
    ↓
Event: EXECUTION_COMPLETE / EXECUTION_FAILED
    ↓
TTS Synthesis (Piper)
    ↓
Speech Output
```

## Threading Model

| Thread | Component | Purpose |
|--------|-----------|---------|
| Main | app._main_loop() | Wake → Listen → Plan → Execute → Speak |
| Per-async-task | EventBus.publish_async | Non-blocking event delivery |
| Per-timeout-task | engine._run_with_timeout | Timeout enforcement thread |
| Per-recurring-task | Scheduler | Delayed/recurring graph execution |

## Configuration

Managed by `ConfigService`:
- Loads from `config.json` with deep merge over defaults
- Dot-notation access: `config.get("models.planner_model")`
- Thread-safe read/write
- Live reload support
- Environment variable override: `JARVIS_CONFIG`

## Migration Strategy

Phase 1 (current): Adapter pattern bridges existing handlers
Phase 2 (next): Migrate planner.py into `src/jarvis/planner/`
Phase 3 (next): Migrate speech into `src/jarvis/speech/`
Phase 4 (next): Migrate memory into `src/jarvis/memory/`
Phase 5 (next): Migrate automation into `src/jarvis/automation/`
Phase 6 (future): REST API via `src/jarvis/api/`

## Key Interfaces

See `src/jarvis/interfaces/` for complete ABC definitions:
- `ASREngine`, `WakeWordEngine`, `TTSEngine` — Speech
- `IntentClassifier`, `Planner`, `CapabilityHandler` — Planning
- `TaskHandler`, `ExecutionEngine`, `ExecutorContext` — Execution
- `MemoryStore`, `SemanticMemory`, `ConversationMemory` — Memory
- `WindowManager`, `UIElement`, `AppLauncher`, `SearchInApp` — Automation
- `ScreenCapture`, `VisionAnalyzer` — Vision
- `PluginHost`, `Plugin` — Plugins
- `EventBus`, `EventSubscriber` — Events

## Security Architecture

- **File Operations**: Sandboxed to `{HOME, CWD, TEMP}`; `C:\Windows`, `C:\Program Files` blocked
- **Terminal Commands**: Character whitelist; dangerous commands blocked
- **PC Control**: Destructive operations require explicit confirmation
- **URL Validation**: Only `http://` and `https://` schemes allowed
- **Plugin Permissions**: Informational capability declaration
- **Process Names**: Sanitized before `taskkill` (alphanumeric only)

## Error Handling Strategy

- All handler-level errors caught and returned as strings (never propagate)
- Planner LLM failures fall back to `ai_chat` handler
- Engine dispatch failures caught per-node in DAG execution
- ASR/TTS failures logged and skipped (non-fatal)
- Memory save is best-effort (never raises)
- Circuit breaker prevents repeated LLM calls after consecutive failures
