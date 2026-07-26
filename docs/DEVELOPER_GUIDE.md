# Developer Guide

## Setting Up the Development Environment

### Prerequisites

```bash
# Python 3.12+
python --version

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Ollama (if not installed)
# Download from https://ollama.com

# Pull required models
ollama pull qwen3.5:4b
ollama pull qwen2.5vl:3b

# Install Piper TTS
# Download piper.exe from https://github.com/rhasspy/piper/releases
# Download a voice model (e.g., en_US-lessac-medium.onnx)
```

### Verify Setup

```bash
python diagnostics.py
# Or from within JARVIS: "run diagnostics"
```

## Codebase Conventions

### Naming

- **Modules**: `snake_case.py` (e.g., `task_executor.py`, `settings_manager.py`)
- **Classes**: `PascalCase` (e.g., `WindowManager`, `JARVISMemory`, `PluginManager`)
- **Functions**: `snake_case` (e.g., `plan_action()`, `execute_plan()`, `register_tool()`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `SUPPORTED_ACTIONS`, `CHECK_INTERVAL_SEC`)
- **Private**: Prefixed with `_` (e.g., `_dispatch()`, `_CTX`, `_FAST_PATH_TRIGGERS`)

### Imports

- Standard library imports first, then third-party, then local
- Local imports use absolute module names
- Heavy imports (tkinter, ollama) are lazy - imported inside function bodies

### Docstrings

Every module and public function has a docstring:
- Module docstring describes purpose and public API
- Function docstring describes arguments, return values, and side effects
- Design notes included where relevant

### Error Handling

- All handler functions return strings (never raise exceptions)
- Use `logger.exception()` for unexpected errors
- Use `logger.warning()` for recoverable failures
- Broad `except Exception` is acceptable at handler boundaries (last resort)
- Destructive operations require explicit user confirmation

### Logging

```python
logger = logging.getLogger("jarvis.module_name")
logger.info("Operation started")
logger.warning("Recoverable issue: %s", detail)
logger.exception("Unexpected error")
```

Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`

## Adding a New Action Handler

### 1. Define the Action

In `planner.py`, add the action name to `SUPPORTED_ACTIONS`:

```python
SUPPORTED_ACTIONS: set[str] = {
    ...
    "my_new_action",
}
```

### 2. Add a Planner Pattern (Optional)

Add a regex pattern to `_FAST_PATH_TRIGGERS` in `planner.py`:

```python
(
    re.compile(
        r"^(?:please\s+)?my\s+command\s+(?P<param>.+?)$",
        re.IGNORECASE,
    ),
    lambda m, src: {"action": "my_new_action", "param": m.group("param")},
),
```

For complex actions, the LLM planner will naturally route to your handler if the regex doesn't match.

### 3. Implement the Handler

In `task_executor.py`, add a handler function:

```python
def _handle_my_new_action(plan: dict, ctx: ExecutorContext) -> str:
    param = (plan.get("param") or "").strip()
    if not param:
        return "I need a parameter, sir."
    try:
        # Implement your logic
        result = do_something(param)
        return f"Operation completed, sir. {result}"
    except Exception as exc:
        logger.exception("my_new_action failed")
        return f"Operation failed, sir. {exc}"
```

### 4. Register the Handler

Add to the `HANDLERS` dict in `task_executor.py`:

```python
HANDLERS: Dict[str, Callable] = {
    ...
    "my_new_action": _handle_my_new_action,
}
```

Registration happens automatically via `register_default_handlers()`.

## Adding a New Module

1. Create the file with a docstring describing its public API
2. Follow the naming conventions above
3. Use the `"jarvis.module_name"` logger
4. Import lazily in the caller (inside functions, not at module level)
5. Export a clean public API documented in the module docstring
6. Update `diagnostics.py` library list if adding a new dependency

## Testing

### Test Files

- `test_plugin_architecture.py` — Plugin system tests
- `test_executor_validation.py` — Executor handler tests
- `test_planner_validation.py` — Planner regex and LLM tests
- `test_production_validation.py` — End-to-end validation

### Writing Tests

```python
# test_my_module.py
from planner import plan_action

def test_simple_command():
    result = plan_action("open Chrome")
    assert result == {"action": "open_app", "app": "Chrome"}

def test_multi_step():
    result = plan_action("open Chrome and search for Python")
    assert "steps" in result
    assert len(result["steps"]) == 2
```

### Running Tests

```bash
python -m pytest test_*.py -v
```

## Debugging Tips

1. **Enable debug logging**: Set `logging.basicConfig(level=logging.DEBUG)` in `jarvis_v2.py`
2. **Test without voice**: Use `python -c "from planner import plan_action; print(plan_action('open Chrome'))"`
3. **Test handlers directly**: `python -c "from task_executor import _handle_time; print(_handle_time({}, {}))"`
4. **Inspect plans**: `print("PLAN:", plan)` is active in the main loop
5. **Check diagnostics**: Run `diagnostics.py` or say "run diagnostics"
6. **View memory files**: Check `memory.json`, `reminders.json`, `Backups/`

## Common Development Tasks

### Add a New Plugin

See the [Plugin Guide](PLUGIN_GUIDE.md) for detailed instructions.

### Modify the System Prompt

Edit `config.json` → `system.system_prompt`, or set it programmatically:

```python
from settings_manager import settings
# Runtime override (not persisted)
```

### Add a New Wake Phrase

```json
{
  "voice": {
    "wake_phrases": ["i'm back", "jarvis", "hey jarvis"]
  }
}
```

### Add a Speech Correction

```python
from speech_correction import add_correction
add_correction("misheard phrase", "correct phrase")
```

Or edit the `CORRECTIONS` dict in `speech_correction.py`.

### Add a Contact for WhatsApp/Email

```python
from whatsapp_actions import add_contact
add_contact("John", "1234567890")

from email_actions import add_recipient
add_recipient("John", "john@example.com")
```
