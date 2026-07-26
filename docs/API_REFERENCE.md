# API Reference

## Core Modules

### `planner.py` — Intent Planning

```
plan_action(user_text: str) -> dict
execute_plan(plan: dict) -> str
register_tool(name: str, handler: callable) -> None
register_folder_alias(name: str, path: str) -> None
```

**`plan_action(text)`**
- Input: User's natural language command
- Output: Action plan dict (single action) or `{"steps": [...]}` (multi-step)
- Behavior: Tries regex fast-path first; falls back to LLM planner
- Edge cases: Returns `{"action": "ai_chat", "text": text}` if no plan matches

**`execute_plan(plan)`**
- Input: Plan dict from `plan_action`
- Output: TTS-friendly response string
- Behavior: Dispatches to registered handlers; executes multi-step plans sequentially

**`register_tool(name, handler)`**
- Registers a handler function for a given action name
- Handler signature: `handler(plan: dict) -> str`

**Plan dict format (single action):**
```python
{"action": "action_name", "param1": "value1", "param2": "value2"}
```

**Plan dict format (multi-step):**
```python
{"steps": [
    {"action": "open_app", "app": "Chrome"},
    {"action": "browser_search", "query": "Python"},
]}
```

### `task_executor.py` — Task Execution

```
set_executor_context(ctx: ExecutorContext) -> None
register_default_handlers() -> None
execute_plan(plan: dict) -> str
set_executor_context_value(key: str, value: str) -> None
get_execution_metrics() -> dict
```

**Handler signatures** (each returns `str`):
```python
def _handle_<action>(plan: dict, ctx: ExecutorContext) -> str
```

### `settings_manager.py` — Configuration

```
SettingsManager.get(key_path: str, default: Any = None) -> Any
SettingsManager.reload() -> None
```

- `key_path`: Dot-notation path (e.g., `"paths.piper_exe"`, `"voice.wake_phrases"`)
- Thread-safe via `threading.Lock`
- Deep-merges user config over defaults

### `ui_core.py` — UI Automation

```
UIAutomator
  .click(x=None, y=None, button="left") -> str
  .double_click(x=None, y=None) -> str
  .right_click(x=None, y=None) -> str
  .type_text(text: str, interval: float = 0.05) -> str
  .press_key(key: str, interval: float = 1.0) -> str
  .hotkey(*keys: str) -> str
  .scroll(direction: str = "down", amount: int = 3) -> str
  .move_mouse(x: int, y: int) -> str
  .focus_window(title: str) -> str
  .wait_for_window(title: str, timeout: float = 15.0) -> str
  .wait_for_element(automation_id=None, text=None, timeout=10.0) -> str

WindowManager
  .get_active_window() -> WindowInfo | None
  .find_windows(title_pattern: str = "") -> list[WindowInfo]
  .find_window_for_app(app_name: str) -> WindowInfo | None
  .focus_window(hwnd: int) -> bool
  .wait_for_window(title: str, timeout: float = 15.0) -> bool

WindowInfo
  .hwnd: int
  .title: str
  .class_name: str
  .process_id: int
  .rect: tuple[int, int, int, int]
  .width: int  (property)
  .height: int  (property)

StrictWindowValidator
  .validate(hwnd: int, app_name: str) -> bool
```

### `search_agent.py` — In-App Search

```
PrioritizedSearchAgent.search(query, app_name, window_hwnd=None) -> SearchResult

SearchResult
  .success: bool
  .message: str
  .method: SearchMethod | None

SearchMethod enum: ACCESSIBILITY, AUTOMATION_ID, OCR, KEYBOARD_SHORTCUT, VISION
```

Prioritized method chain: Keyboard Shortcut → Accessibility → OCR → Vision.

### `app_launcher.py` — Application Launching

```
AppDiscovery.discover_all_apps() -> dict[str, dict]
AppLauncher.launch_and_verify(app_name, wait_for_ui=False) -> LaunchResult

LaunchResult
  .status: LaunchStatus
  .message: str
  .process_id: int | None
  .window_title: str | None
  .hwnd: int | None
  .search_ready: bool

LaunchStatus enum: SUCCESS, PROCESS_NOT_FOUND, WINDOW_NOT_FOUND, FOCUS_FAILED, UI_NOT_READY, LAUNCH_FAILED
```

### `memory.py` — Legacy Memory

```
load() -> dict        # Returns {"facts": [str, ...]}
save(data: dict) -> None
```

### `memory_v2.py` — Multi-Tier Memory

```
JARVISMemory (main class)
  .load() -> dict                          # Backward compat: returns {"facts": [...]}
  .save(data: dict) -> None                # Backward compat: saves facts from dict
  .add_short_term(content, **kwargs) -> str
  .search_short_term(query, **kwargs) -> list[SearchResult]
  .add_long_term(content, **kwargs) -> str
  .search_long_term(query, **kwargs) -> list[SearchResult]
  .start_project(project_id, description) -> bool
  .set_project_item(project_id, key, value) -> bool
  .get_project_item(project_id, key) -> Any
  .add_conversation_turn(speaker, text, **kwargs) -> int
  .get_recent_conversation(limit=10) -> list[ConversationTurn]
  .get_conversation_summary() -> str
  .save_preference(key, value) -> None
  .get_preference(key) -> Any
  .get_user_facts(limit=20) -> list[str]
  .get_statistics() -> dict
  .cleanup_expired() -> dict[str, int]
  .export_all() -> dict
  .import_all(data) -> dict
  .save_backup(backup_dir="backups") -> str
  .load_backup(backup_file) -> bool

MemoryItem
  .id: str
  .content: str
  .timestamp: datetime
  .category: str          # fact, preference, event, insight
  .importance: int        # 1-10
  .ttl_days: int | None
  .source: str
  .correlations: list[str]
  .tags: list[str]
  .metadata: dict

SearchResult
  .item: MemoryItem
  .score: float
  .match_type: str       # exact, semantic, temporal

ConversationTurn
  .timestamp: datetime
  .speaker: str          # user or jarvis
  .text: str
  .plan: dict | None
  .executed: bool
  .outcome: str | None
```

### `session_memory.py` — Session Context

```
get(key: str) -> str
set(key: str, value: str) -> None
push_action(action: dict) -> None
clear() -> None
resolve_pronoun(text: str) -> str
update_from_plan(plan: dict) -> None
```

Session keys: `current_app`, `current_window`, `current_folder`, `current_file`, `current_browser_tab`, `clipboard_contents`, `last_search_query`, `recent_actions`

### `file_manager.py` — File Operations

```
run(op: str, **params) -> dict
list_ops() -> list[str]
```

Supported operations: `create_file`, `read_file`, `write_file`, `append_file`, `delete_file`, `rename_file`, `move_file`, `copy_file`, `search_files`, `create_folder`, `delete_folder`, `rename_folder`, `list_folder`

Return dict: `{"ok": bool, "tts": str, "op": str, "data": dict, "path": str}`

### `pc_control.py` — System Control

```
execute(op: str, confirm_fn=None) -> dict
is_destructive(op: str) -> bool
list_commands() -> list[str]
```

Return dict: `{"ok": bool, "tts": str, "op": str}`

Operators: lock, sleep, logoff, shutdown, restart, open (folders/admin tools)

### `reminders.py` — Reminder Engine

```
add_reminder(time_str: str, task: str) -> dict
remove_reminder(index: int) -> bool
list_reminders() -> list[dict]
clear_reminders() -> int
start_checker(speak_fn: callable) -> None
```

### `calendar_engine.py` — Calendar Events

```
create_calendar_event(title, date, time, duration_minutes=60) -> dict
generate_ics(title, start_dt, duration_minutes=60, description="") -> str
parse_when(text) -> datetime | None
```

### `clipboard_tools.py` — Clipboard

```
read() -> str
write(text: str) -> bool
clear() -> bool
summarize(chat_fn=None) -> str
```

### `email_actions.py` — Email

```
compose_email(recipient, subject, body, confirm_fn=None) -> dict
add_recipient(name, email) -> None
resolve_recipient(name) -> tuple[str, bool]
```

### `whatsapp_actions.py` — WhatsApp

```
send_whatsapp_message(contact, message, confirm_fn=None, auto_open=True) -> dict
add_contact(name, phone_e164) -> None
resolve_contact(contact) -> tuple[str, bool]
```

### `code_generator.py` — Code Generation

```
generate_code(description, language="") -> dict
validate_syntax(code, language) -> tuple[bool, str]
write_code_to_file(code, path) -> dict
```

### `speech_correction.py` — ASR Corrections

```
correct(text: str) -> str
add_correction(wrong: str, right: str) -> None
load_corrections(path: str) -> None
```

### `diagnostics.py` — Environment Checks

```
check_environment() -> dict
print_report(report) -> None
get_report_text(report) -> str
```

## Plugin System

### `plugins/__init__.py`

```
Plugin (base class)
  .__init__(context: dict)
  .metadata: PluginMetadata
  .on_load() -> bool
  .on_unload() -> None
  .register_tools() -> dict[str, callable]
  .register_handlers() -> dict[str, callable]
  .register_commands() -> dict[str, callable]
  .on_message(text: str) -> str | None

PluginMetadata
  .name: str
  .version: str
  .description: str
  .author: str
  .permissions: list[str]
  .dependencies: list[str]
  .enabled: bool
  .plugin_type: str
  .min_jarvis_version: str

PluginManager
  .discover() -> list[str]
  .load_plugin(module_name) -> bool
  .load_all() -> int
  .unload_plugin(module_name) -> bool
  .hot_reload(module_name) -> bool
  .hot_reload_all() -> int
  .enable_plugin(module_name) -> bool
  .disable_plugin(module_name) -> bool
  .list_plugins() -> list[dict]
  .get_plugin(module_name) -> Plugin | None
  .get_all_tools() -> dict[str, callable]
  .call_tool(name, plan) -> str | None
```

### `plugins/agents/__init__.py`

```
EventBus
  .subscribe(event_type, callback) -> None
  .publish(event) -> None
  .unsubscribe(event_type, callback) -> None

MessageQueue
  .send(message) -> None
  .receive(timeout=None) -> AgentEvent | None

AgentOrchestrator
  .register_agent(agent) -> None
  .start_all_agents() -> None
  .stop_all_agents() -> None
  .assign_task(task, target_agent=None) -> bool
  .list_agents() -> list[dict]

BaseAgent
  .start() -> None
  .stop() -> None
  .pause() -> None
  .resume() -> None
  .process_event(event) -> None
  .state: AgentState
```

## Supported Actions (Complete List)

```
open_app              close_app             switch_window
focus_window          web_search            search_in_app
search_in_app_v2      reminder              set_reminder
calendar_event        clipboard             file_operation
folder_operation      pc_control            email
whatsapp              screenshot            screen_awareness
system_control        volume_control        memory_store
memory_recall         memory_clear          time
date                  diagnostics           system_stats
music                 click                 double_click
right_click           move_mouse            type_text
press_key             hotkey                scroll
browser_open          browser_search        browser_click
run_program           run_terminal_command  generate_code
wait                  wait_for_window       wait_for_element
ai_chat
```
