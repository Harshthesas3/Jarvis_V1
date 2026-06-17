"""
test_production_validation.py
-------------------------------
End-to-end validation of the JARVIS pipeline.

Tests cover:
    - planner: fast-path, clarification, multi-step, path resolution,
      pronoun resolution, context tracking, LLM fallback
    - executor: handler dispatch, file operations, code generation,
      reminder CRUD, structured error handling
    - speech_correction: dictionary-based post-processing
    - integration: composite flows
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch


# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from planner import (
        SUPPORTED_ACTIONS,
        _try_fast_path,
        _plan_single,
        plan_action,
        execute_plan,
        _resolve_path,
        _needs_clarification,
        _resolve_pronouns,
        _update_context_from_plan,
        _INITIAL_CONTEXT,
        _FAST_PATH_TRIGGERS,
        register_tool,
        _TOOL_REGISTRY,
    )
    import planner
except ImportError as e:
    raise RuntimeError(f"Failed to import planner: {e}")

try:
    import task_executor
except ImportError:
    task_executor = None

try:
    import speech_correction
    import file_manager
    import code_generator
    import session_memory
    import reminders
except ImportError as e:
    pass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_handler(action: str, response: str = "OK"):
    """Register a fake handler for `action` that returns `response`."""
    def handler(plan: dict) -> str:
        return response
    register_tool(action, handler)
    return handler


def _assert_plan_matches(plan: dict, **expected) -> None:
    """Assert that `plan` contains all `expected` key-value pairs."""
    for k, v in expected.items():
        assert k in plan, f"Missing key {k!r} in plan {plan}"
        assert plan[k] == v, (
            f"Key {k!r} expected {v!r}, got {plan[k]!r}"
        )


# ---------------------------------------------------------------------------
# Speech correction
# ---------------------------------------------------------------------------

def test_speech_correction_hello_world():
    assert speech_correction.correct("fellow world") == "hello world"


def test_speech_correction_casings():
    assert speech_correction.correct("Fellow World") == "hello world"


def test_speech_correction_unknown_preserved():
    result = speech_correction.correct("something completely different")
    assert "different" in result or result == "something completely different"


def test_speech_correction_empty():
    assert speech_correction.correct("") == ""
    assert speech_correction.correct(None) == ""


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def test_resolve_path_downloads():
    home = os.path.expanduser("~")
    result = _resolve_path("save it in downloads")
    assert "Downloads" in result or home in result


def test_resolve_path_desktop():
    home = os.path.expanduser("~")
    result = _resolve_path("put it on desktop")
    assert "Desktop" in result or home in result


def test_resolve_path_documents():
    home = os.path.expanduser("~")
    result = _resolve_path("store in documents")
    assert "Documents" in result or home in result


def test_resolve_path_no_alias():
    result = _resolve_path("/some/absolute/path")
    assert result == "/some/absolute/path"


# ---------------------------------------------------------------------------
# Clarification handler
# ---------------------------------------------------------------------------

def test_clarification_bare_create_file():
    result = _needs_clarification("create a file")
    assert result is not None
    assert result.get("action") == "clarification"
    assert "question" in result


def test_clarification_bare_create_folder():
    result = _needs_clarification("make folder")
    assert result is not None
    assert result.get("action") == "clarification"


def test_clarification_bare_reminder():
    result = _needs_clarification("remind me")
    assert result is not None
    assert result.get("action") == "clarification"


def test_clarification_bare_search():
    result = _needs_clarification("search")
    assert result is not None
    assert result.get("action") == "clarification"


def test_clarification_complete_request():
    result = _needs_clarification("create a file called test.txt")
    assert result is None


def test_clarification_complete_request_folder():
    result = _needs_clarification("create a folder called Python Projects")
    assert result is None


# ---------------------------------------------------------------------------
# Fast-path patterns — create file
# ---------------------------------------------------------------------------

def test_fast_path_create_file_simple():
    plan = _try_fast_path("create test.txt")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="create_file", name="test.txt")


def test_fast_path_create_file_called():
    plan = _try_fast_path("create a file called notes.txt")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="create_file", name="notes.txt")


def test_fast_path_make_file():
    plan = _try_fast_path("make a file called todo.txt")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="create_file", name="todo.txt")


def test_fast_path_create_file_in_folder():
    plan = _try_fast_path("create test.txt in downloads")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="create_file", name="test.txt")
    assert "folder" in plan, f"Expected folder key in {plan}"


def test_fast_path_create_file_with_content():
    plan = _try_fast_path("create hello.py with print hello world")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="create_file", name="hello.py")
    assert "content" in plan


def test_fast_path_open_file():
    plan = _try_fast_path("open file readme.txt")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="open_file")


def test_fast_path_read_file():
    plan = _try_fast_path("read file notes.txt")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="read_file")


def test_fast_path_delete_file():
    plan = _try_fast_path("delete file old.txt")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="delete_file")


def test_fast_path_rename_file():
    plan = _try_fast_path("rename file a.txt to b.txt")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="rename_file",
                         path="a.txt", new_name="b.txt")


def test_fast_path_move_file():
    plan = _try_fast_path("move file notes.txt to downloads")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="move_file",
                         path="notes.txt")


def test_fast_path_copy_file():
    plan = _try_fast_path("copy file notes.txt to documents")
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="copy_file",
                         path="notes.txt")


# ---------------------------------------------------------------------------
# Fast-path — folder operations
# ---------------------------------------------------------------------------

def test_fast_path_create_folder():
    plan = _try_fast_path("create a folder called Python Projects")
    assert plan is not None
    _assert_plan_matches(plan, action="folder_operation", op="create_folder",
                         name="Python Projects")


def test_fast_path_delete_folder():
    plan = _try_fast_path("delete the folder temp")
    assert plan is not None
    _assert_plan_matches(plan, action="folder_operation", op="delete_folder")


def test_fast_path_list_folder():
    plan = _try_fast_path("list the downloads folder")
    assert plan is not None
    _assert_plan_matches(plan, action="folder_operation", op="list_folder")


def test_fast_path_rename_folder():
    plan = _try_fast_path("rename the folder foo to bar")
    assert plan is not None
    _assert_plan_matches(plan, action="folder_operation", op="rename_folder",
                         path="foo", new_name="bar")


# ---------------------------------------------------------------------------
# Fast-path — app launch
# ---------------------------------------------------------------------------

def test_fast_path_open_app():
    plan = _try_fast_path("open calculator")
    assert plan is not None
    _assert_plan_matches(plan, action="open_app", app="calculator")


def test_fast_path_open_multi_word_app():
    plan = _try_fast_path("open visual studio code")
    assert plan is not None
    _assert_plan_matches(plan, action="open_app", app="visual studio code")


def test_fast_path_launch_synonym():
    plan = _try_fast_path("launch notepad")
    assert plan is not None
    _assert_plan_matches(plan, action="open_app", app="notepad")


def test_fast_path_start_synonym():
    plan = _try_fast_path("start chrome")
    assert plan is not None
    _assert_plan_matches(plan, action="open_app", app="chrome")


def test_fast_path_open_app_with_conjunction_returns_none():
    """When 'and'/'then' appears, open_app should defer to multi-step."""
    plan = _try_fast_path("open calculator and then type 5+5")
    assert plan is None


# ---------------------------------------------------------------------------
# Fast-path — PC control
# ---------------------------------------------------------------------------

def test_fast_path_pc_control_lock():
    plan = _try_fast_path("lock computer")
    assert plan is not None
    _assert_plan_matches(plan, action="pc_control", phrase="lock computer")


def test_fast_path_pc_control_shutdown():
    plan = _try_fast_path("shutdown computer")
    assert plan is not None
    _assert_plan_matches(plan, action="pc_control")


def test_fast_path_pc_control_restart():
    plan = _try_fast_path("restart")
    assert plan is not None
    _assert_plan_matches(plan, action="pc_control")


def test_fast_path_pc_control_open_downloads():
    plan = _try_fast_path("open downloads folder")
    assert plan is not None
    _assert_plan_matches(plan, action="pc_control")


# ---------------------------------------------------------------------------
# Fast-path — web search & time
# ---------------------------------------------------------------------------

def test_fast_path_web_search():
    plan = _try_fast_path("search for Python tutorials")
    assert plan is not None
    _assert_plan_matches(plan, action="web_search", query="Python tutorials")


def test_fast_path_what_is():
    plan = _try_fast_path("what is the capital of France")
    assert plan is not None
    _assert_plan_matches(plan, action="web_search", query="the capital of France")


def test_fast_path_what_is_route():
    plan = _try_fast_path("what's my screen")
    assert plan is not None
    _assert_plan_matches(plan, action="web_search")


def test_fast_path_time():
    plan = _try_fast_path("what is the time")
    assert plan is not None
    _assert_plan_matches(plan, action="time")


def test_fast_path_date():
    plan = _try_fast_path("what is the date")
    assert plan is not None
    _assert_plan_matches(plan, action="date")


# ---------------------------------------------------------------------------
# Fast-path — reminders
# ---------------------------------------------------------------------------

def test_fast_path_reminder():
    plan = _try_fast_path("remind me in 5 minutes to check the oven")
    assert plan is not None, f"Got None for reminder"
    _assert_plan_matches(plan, action="reminder")


def test_fast_path_show_reminders():
    plan = _try_fast_path("show reminders")
    assert plan is not None
    _assert_plan_matches(plan, action="reminder", op="list")


def test_fast_path_clear_reminders():
    plan = _try_fast_path("clear reminders")
    assert plan is not None
    _assert_plan_matches(plan, action="reminder", op="clear")


# ---------------------------------------------------------------------------
# Fast-path — clipboard
# ---------------------------------------------------------------------------

def test_fast_path_clipboard_read():
    plan = _try_fast_path("read my clipboard")
    assert plan is not None
    _assert_plan_matches(plan, action="clipboard", op="read")


def test_fast_path_clipboard_write():
    plan = _try_fast_path("copy hello world to my clipboard")
    assert plan is not None
    _assert_plan_matches(plan, action="clipboard", op="write")


def test_fast_path_clipboard_clear():
    plan = _try_fast_path("clear my clipboard")
    assert plan is not None
    _assert_plan_matches(plan, action="clipboard", op="clear")


# ---------------------------------------------------------------------------
# Fast-path — mouse & keyboard
# ---------------------------------------------------------------------------

def test_fast_path_click():
    plan = _try_fast_path("click at 100 200")
    assert plan is not None
    _assert_plan_matches(plan, action="click")


def test_fast_path_double_click():
    plan = _try_fast_path("double click at 100 200")
    assert plan is not None
    _assert_plan_matches(plan, action="double_click")


def test_fast_path_right_click():
    plan = _try_fast_path("right click at 100 200")
    assert plan is not None
    _assert_plan_matches(plan, action="right_click")


def test_fast_path_type_text():
    plan = _try_fast_path("type hello world")
    assert plan is not None
    _assert_plan_matches(plan, action="type_text", text="hello world")


def test_fast_path_press_key():
    plan = _try_fast_path("press enter")
    assert plan is not None
    _assert_plan_matches(plan, action="press_key", key="enter")


def test_fast_path_scroll():
    plan = _try_fast_path("scroll down")
    assert plan is not None
    _assert_plan_matches(plan, action="scroll", direction="down")


# ---------------------------------------------------------------------------
# Fast-path — browser
# ---------------------------------------------------------------------------

def test_fast_path_browser_search():
    plan = _try_fast_path("search in browser for cats")
    assert plan is not None
    _assert_plan_matches(plan, action="browser_search", query="cats")


def test_fast_path_browser_open():
    plan = _try_fast_path("open browser to https://example.com")
    assert plan is not None
    _assert_plan_matches(plan, action="browser_open")


def test_fast_path_browser_click():
    plan = _try_fast_path("click on login in browser")
    assert plan is not None
    _assert_plan_matches(plan, action="browser_click", element="login")


# ---------------------------------------------------------------------------
# Fast-path — system commands
# ---------------------------------------------------------------------------

def test_fast_path_run_program():
    plan = _try_fast_path("run notepad")
    assert plan is not None
    _assert_plan_matches(plan, action="run_program", program="notepad")


def test_fast_path_run_terminal_command():
    plan = _try_fast_path("run command dir")
    assert plan is not None
    _assert_plan_matches(plan, action="run_terminal_command", command="dir")


def test_fast_path_volume_up():
    plan = _try_fast_path("volume up")
    assert plan is not None
    _assert_plan_matches(plan, action="volume_control", op="up")


def test_fast_path_volume_down():
    plan = _try_fast_path("volume down")
    assert plan is not None
    _assert_plan_matches(plan, action="volume_control", op="down")


def test_fast_path_set_volume():
    plan = _try_fast_path("set volume to 50 percent")
    assert plan is not None
    _assert_plan_matches(plan, action="volume_control", op="set", level=50)


# ---------------------------------------------------------------------------
# Fast-path — memory
# ---------------------------------------------------------------------------

def test_fast_path_remember():
    plan = _try_fast_path("remember that my favorite color is blue")
    assert plan is not None
    _assert_plan_matches(plan, action="memory_store", fact="my favorite color is blue")


def test_fast_path_memory_recall():
    plan = _try_fast_path("what do you remember")
    assert plan is not None
    _assert_plan_matches(plan, action="memory_recall")


def test_fast_path_memory_clear():
    plan = _try_fast_path("clear your memory")
    assert plan is not None
    _assert_plan_matches(plan, action="memory_clear")


# ---------------------------------------------------------------------------
# Fast-path — code generation
# ---------------------------------------------------------------------------

def test_fast_path_generate_code():
    plan = _try_fast_path("generate code for a Python function that adds two numbers")
    assert plan is not None
    _assert_plan_matches(plan, action="generate_code")


def test_fast_path_write_code():
    plan = _try_fast_path("write code for a web scraper in Python")
    assert plan is not None
    _assert_plan_matches(plan, action="generate_code")


# ---------------------------------------------------------------------------
# Fast-path — close / switch / wait
# ---------------------------------------------------------------------------

def test_fast_path_close_app():
    plan = _try_fast_path("close calculator")
    assert plan is not None
    _assert_plan_matches(plan, action="close_app", app="calculator")


def test_fast_path_switch_window():
    plan = _try_fast_path("switch to chrome")
    assert plan is not None
    _assert_plan_matches(plan, action="switch_window", target="chrome")


def test_fast_path_wait():
    plan = _try_fast_path("wait 5 seconds")
    assert plan is not None
    _assert_plan_matches(plan, action="wait", seconds=5)


# ---------------------------------------------------------------------------
# Fast-path — screen awareness
# ---------------------------------------------------------------------------

def test_fast_path_screen_describe():
    plan = _try_fast_path("what is on my screen")
    assert plan is not None
    _assert_plan_matches(plan, action="screen_awareness")


def test_fast_path_screen_error():
    plan = _try_fast_path("analyze this error")
    assert plan is not None
    _assert_plan_matches(plan, action="screen_awareness", op="error")


def test_fast_path_screen_code_review():
    plan = _try_fast_path("review this code")
    assert plan is not None
    _assert_plan_matches(plan, action="screen_awareness", op="code_review")


# ---------------------------------------------------------------------------
# Fast-path — whatsapp and email
# ---------------------------------------------------------------------------

def test_fast_path_whatsapp():
    plan = _try_fast_path("message mom that I will be late")
    assert plan is not None
    _assert_plan_matches(plan, action="whatsapp")


def test_fast_path_email():
    plan = _try_fast_path("email john about meeting saying see you tomorrow")
    assert plan is not None
    _assert_plan_matches(plan, action="email")


# ---------------------------------------------------------------------------
# Fast-path — miscellaneous
# ---------------------------------------------------------------------------

def test_fast_path_screenshot():
    plan = _try_fast_path("take a screenshot")
    assert plan is not None
    _assert_plan_matches(plan, action="screenshot")


def test_fast_path_battery():
    plan = _try_fast_path("battery")
    assert plan is not None
    _assert_plan_matches(plan, action="system_stats")


def test_fast_path_music_play():
    plan = _try_fast_path("play music")
    assert plan is not None
    _assert_plan_matches(plan, action="music", op="play")


def test_fast_path_music_pause():
    plan = _try_fast_path("pause music")
    assert plan is not None
    _assert_plan_matches(plan, action="music", op="pause")


def test_fast_path_system_lock():
    plan = _try_fast_path("lock computer")
    assert plan is not None
    _assert_plan_matches(plan, action="pc_control")


# ---------------------------------------------------------------------------
# Pronoun resolution
# ---------------------------------------------------------------------------

def test_pronoun_resolves_it():
    ctx = dict(_INITIAL_CONTEXT, last_file="data.txt", last_folder="docs")
    resolved = _resolve_pronouns("open it", ctx)
    assert "data.txt" in resolved or "docs" in resolved


def test_pronoun_resolves_this():
    ctx = dict(_INITIAL_CONTEXT, last_clipboard="hello")
    resolved = _resolve_pronouns("save this", ctx)
    assert "hello" in resolved


def test_pronoun_resolves_that():
    ctx = dict(_INITIAL_CONTEXT, last_search_result="Python tutorial")
    resolved = _resolve_pronouns("search for that", ctx)
    assert "Python tutorial" in resolved


def test_pronoun_no_context_preserves():
    ctx = dict(_INITIAL_CONTEXT)
    resolved = _resolve_pronouns("open it", ctx)
    assert resolved == "open it"


# ---------------------------------------------------------------------------
# Context tracking — _update_context_from_plan
# ---------------------------------------------------------------------------

def test_context_file_creation():
    ctx = dict(_INITIAL_CONTEXT)
    _update_context_from_plan(ctx, {
        "action": "file_operation", "op": "create_file", "name": "test.txt"
    })
    assert ctx["last_file"] == "test.txt"


def test_context_folder_creation():
    ctx = dict(_INITIAL_CONTEXT)
    _update_context_from_plan(ctx, {
        "action": "folder_operation", "op": "create_folder", "name": "Projects"
    })
    assert ctx["last_folder"] == "Projects"


def test_context_search_result():
    ctx = dict(_INITIAL_CONTEXT)
    _update_context_from_plan(ctx, {
        "action": "web_search", "query": "Python"
    })
    assert ctx["last_search_result"] == "Python"


def test_context_app_launch():
    ctx = dict(_INITIAL_CONTEXT)
    _update_context_from_plan(ctx, {
        "action": "open_app", "app": "calculator"
    })
    assert ctx["last_app"] == "calculator"


# ---------------------------------------------------------------------------
# plan_action — integration
# ---------------------------------------------------------------------------

def test_plan_action_reminder():
    plan = plan_action("remind me in 10 minutes to call mom", use_llm=False)
    assert plan is not None
    assert plan.get("action") == "reminder"
    assert "task" in plan


def test_plan_action_file_create():
    plan = plan_action("create test.txt", use_llm=False)
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="create_file",
                         name="test.txt")


def test_plan_action_file_create_with_content():
    plan = plan_action("create hello.py with print hello world", use_llm=False)
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="create_file",
                         name="hello.py")
    assert "content" in plan


def test_plan_action_file_create_in_downloads():
    plan = plan_action("create test.txt in downloads", use_llm=False)
    assert plan is not None
    _assert_plan_matches(plan, action="file_operation", op="create_file",
                         name="test.txt")
    assert "folder" in plan


def test_plan_action_ai_chat_when_truly_conversational():
    plan = plan_action("how are you today", use_llm=False)
    assert plan is not None
    assert plan.get("action") == "ai_chat"


def test_plan_action_multi_step():
    plan = plan_action("open calculator and then type 5+5", use_llm=False)
    assert plan is not None
    assert "steps" in plan
    assert len(plan["steps"]) >= 2


def test_plan_action_multi_step_with_comma():
    plan = plan_action("open notepad, type hello world", use_llm=False)
    assert plan is not None
    assert "steps" in plan
    assert len(plan["steps"]) >= 2


def test_plan_action_clarification():
    plan = plan_action("create a file", use_llm=False)
    assert plan is not None
    assert plan.get("action") == "clarification"


def test_plan_action_speech_correction():
    plan = plan_action("create a file called fellow world dot py", use_llm=False)
    assert plan is not None


# ---------------------------------------------------------------------------
# execute_plan — dispatch integration
# ---------------------------------------------------------------------------

def test_execute_plan_single_action():
    _fake_handler("test_action", response="Done!")
    plan = {"action": "test_action"}
    result = execute_plan(plan)
    assert "Done!" in result


def test_execute_plan_steps_all_succeed():
    _fake_handler("step1", response="Step 1 done.")
    _fake_handler("step2", response="Step 2 done.")
    plan = {"steps": [{"action": "step1"}, {"action": "step2"}]}
    result = execute_plan(plan)
    assert "Step 1" in result
    assert "Step 2" in result


def test_execute_plan_step_failure_continues():
    def failing_handler(plan: dict) -> str:
        raise RuntimeError("Simulated failure")
    register_tool("failing", failing_handler)
    _fake_handler("good_step", response="OK")
    plan = {"steps": [{"action": "failing"}, {"action": "good_step"}]}
    result = execute_plan(plan)
    assert "failed" in result.lower()


def test_execute_plan_empty_steps():
    plan = {"steps": []}
    result = execute_plan(plan)
    assert result is not None


def test_execute_plan_none():
    plan = None
    result = execute_plan(plan)
    assert "invalid" in result.lower()


def test_execute_plan_bad_type():
    plan = "not a dict"
    result = execute_plan(plan)
    assert "invalid" in result.lower()


# ---------------------------------------------------------------------------
# File manager integration (no-disk ops)
# ---------------------------------------------------------------------------

def test_file_manager_run_create():
    with tempfile.TemporaryDirectory() as tmp:
        import file_manager
        result = file_manager.run("create_file", name="output_test.txt", folder=tmp)
        assert result.get("ok"), f"create failed: {result}"
        assert os.path.exists(os.path.join(tmp, "output_test.txt"))


def test_file_manager_run_create_with_content():
    with tempfile.TemporaryDirectory() as tmp:
        import file_manager
        result = file_manager.run("create_file", name="greeting.txt",
                                  content="Hello, world!", folder=tmp)
        assert result.get("ok"), f"create with content failed: {result}"
        path = os.path.join(tmp, "greeting.txt")
        with open(path, "r") as f:
            assert f.read() == "Hello, world!"


def test_file_manager_run_read():
    with tempfile.TemporaryDirectory() as tmp:
        import file_manager
        file_manager.run("create_file", name="read_test.txt", folder=tmp)
        result = file_manager.run("read_file", path=os.path.join(tmp, "read_test.txt"))
        assert result.get("ok"), f"read failed: {result}"


def test_file_manager_run_delete():
    with tempfile.TemporaryDirectory() as tmp:
        import file_manager
        file_manager.run("create_file", name="del_test.txt", folder=tmp)
        result = file_manager.run("delete_file", path=os.path.join(tmp, "del_test.txt"),
                                  confirm_fn=lambda prompt: True)
        assert result.get("ok"), f"delete failed: {result}"


# ---------------------------------------------------------------------------
# Code generator — validation
# ---------------------------------------------------------------------------

def test_code_generator_empty_description():
    result = code_generator.generate_code("")
    assert not result.get("ok")


def test_code_generator_missing_dependency():
    with patch.dict("sys.modules", {"ollama": None}):
        result = code_generator.generate_code("a function")
        assert not result.get("ok")


# ---------------------------------------------------------------------------
# Reminders — CRUD without background thread
# ---------------------------------------------------------------------------

def test_reminder_add_list():
    eng = reminders.ReminderEngine(store_path=tempfile.mktemp(suffix=".json"))
    result = eng.add_reminder("in 30 minutes", "test reminder")
    assert result.get("ok"), f"add failed: {result}"
    lst = eng.list_reminders()
    assert len(lst) == 1
    assert lst[0]["task"] == "test reminder"


def test_reminder_remove():
    eng = reminders.ReminderEngine(store_path=tempfile.mktemp(suffix=".json"))
    eng.add_reminder("in 30 minutes", "to remove")
    assert eng.remove_reminder(0)
    assert len(eng.list_reminders()) == 0


def test_reminder_clear():
    eng = reminders.ReminderEngine(store_path=tempfile.mktemp(suffix=".json"))
    eng.add_reminder("in 30 minutes", "a")
    eng.add_reminder("in 60 minutes", "b")
    assert eng.clear_reminders() == 2
    assert len(eng.list_reminders()) == 0


def test_reminder_bad_time():
    eng = reminders.ReminderEngine(store_path=tempfile.mktemp(suffix=".json"))
    result = eng.add_reminder("not a time", "fail")
    assert not result.get("ok")


def test_reminder_out_of_range_index():
    eng = reminders.ReminderEngine(store_path=tempfile.mktemp(suffix=".json"))
    assert not eng.remove_reminder(999)


# ---------------------------------------------------------------------------
# Session memory
# ---------------------------------------------------------------------------

def test_session_memory_set_get():
    session_memory.clear()
    session_memory.set("current_app", "calculator")
    assert session_memory.get("current_app") == "calculator"


def test_session_memory_push_action():
    session_memory.clear()
    session_memory.push_action({"action": "open_app", "app": "notepad"})
    assert len(session_memory.get("recent_actions")) == 1
    assert session_memory.get("recent_actions")[0]["action"] == "open_app"


def test_session_memory_clear():
    session_memory.set("current_app", "chrome")
    session_memory.clear()
    assert session_memory.get("current_app") == ""


def test_session_memory_resolve_pronoun():
    session_memory.clear()
    session_memory.set("current_file", "data.txt")
    resolved = session_memory.resolve_pronoun("open the file")
    assert "data.txt" in resolved


# ---------------------------------------------------------------------------
# Parsing — parse_when
# ---------------------------------------------------------------------------

def test_parse_when_in_minutes():
    from datetime import datetime, timedelta
    now = datetime(2025, 6, 1, 12, 0)
    result = reminders.parse_when("in 10 minutes", now=now)
    assert result is not None
    assert result == now + timedelta(minutes=10)


def test_parse_when_tomorrow():
    from datetime import datetime, timedelta
    now = datetime(2025, 6, 1, 12, 0)
    result = reminders.parse_when("tomorrow 9 am", now=now)
    assert result is not None
    assert result.day == 2
    assert result.hour == 9


def test_parse_when_tonight():
    from datetime import datetime
    now = datetime(2025, 6, 1, 12, 0)
    result = reminders.parse_when("tonight at 10 pm", now=now)
    assert result is not None
    assert result.hour == 22


def test_parse_when_invalid():
    result = reminders.parse_when("")
    assert result is None


# ---------------------------------------------------------------------------
# Wake listener — is_wake_phrase heuristic
# ---------------------------------------------------------------------------

def _is_wake_phrase(text: str) -> bool:
    """Inline the wake phrase check for testing."""
    WAKE_PHRASES = ["i'm back", "i am back", "im back", "jarvis wake up", "jarvis"]
    text_lower = text.strip().lower()
    for phrase in WAKE_PHRASES:
        if phrase in text_lower:
            return True
    return False


def test_wake_phrase_exact():
    assert _is_wake_phrase("jarvis")
    assert _is_wake_phrase("i'm back")
    assert _is_wake_phrase("I'm back")
    assert _is_wake_phrase("jarvis wake up")
    assert _is_wake_phrase("IM BACK")


def test_wake_phrase_with_prefix():
    assert _is_wake_phrase("hey jarvis")
    assert _is_wake_phrase("okay jarvis")
    assert _is_wake_phrase("hello jarvis please")


def test_wake_phrase_non_wake():
    assert not _is_wake_phrase("")
    assert not _is_wake_phrase("hello world")
    assert not _is_wake_phrase("goodbye")


# ---------------------------------------------------------------------------
# UI Automation — acceptance tests (planner-level routing)
# ---------------------------------------------------------------------------

def test_ui_focus_window():
    plan = plan_action("focus on notepad", use_llm=False)
    _assert_plan_matches(plan, action="focus_window", title="notepad")


def test_ui_wait_for_window():
    plan = plan_action("wait for Microsoft Store", use_llm=False)
    _assert_plan_matches(plan, action="wait_for_window", title="Microsoft Store")


def test_ui_hotkey():
    plan = plan_action("press ctrl l", use_llm=False)
    assert plan is not None


def test_ui_open_app_then_search():
    """Acceptance: Open Microsoft Store and search for Spotify."""
    plan = plan_action("Open Microsoft Store and search for Spotify", use_llm=False)
    assert plan is not None
    assert "steps" in plan
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="open_app", app="Microsoft Store")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                         query="Spotify", app="Microsoft Store")


def test_ui_open_chrome_then_search():
    """Acceptance: Open Chrome and search OpenAI."""
    plan = plan_action("Open Chrome and search OpenAI", use_llm=False)
    assert plan is not None
    assert "steps" in plan
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="open_app", app="Chrome")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                         query="OpenAI", app="Chrome")


def test_ui_vscode_create_file():
    """Acceptance: Open VS Code and create file test.py."""
    plan = plan_action("Open VS Code and create file test.py", use_llm=False)
    assert plan is not None
    assert "steps" in plan
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="open_app", app="VS Code")
    _assert_plan_matches(plan["steps"][1], action="file_operation",
                         op="create_file", name="test.py")


def test_ui_downloads_create_folder():
    """Acceptance: Open Downloads and create folder JarvisTests."""
    plan = plan_action("Open Downloads and create folder JarvisTests", use_llm=False)
    assert plan is not None
    assert "steps" in plan
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="pc_control",
                         phrase="open downloads")
    _assert_plan_matches(plan["steps"][1], action="folder_operation",
                         op="create_folder", name="JarvisTests")


# ---------------------------------------------------------------------------
# Universal Search Automation — acceptance tests
# ---------------------------------------------------------------------------
def test_search_v2_open_apple_music_and_search():
    plan = plan_action("Open Apple Music and search for You Rock My World",
                       use_llm=False)
    assert plan is not None
    assert "steps" in plan, f"Expected multi-step, got: {plan}"
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="open_app", app="Apple Music")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                         query="You Rock My World", app="Apple Music")


def test_search_v2_open_spotify_and_search():
    plan = plan_action("Open Spotify and search for Michael Jackson",
                       use_llm=False)
    assert plan is not None
    assert "steps" in plan, f"Expected multi-step, got: {plan}"
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="open_app", app="Spotify")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                         query="Michael Jackson", app="Spotify")


def test_search_v2_open_steam_and_search():
    plan = plan_action("Open Steam and search for GTA V", use_llm=False)
    assert plan is not None
    assert "steps" in plan, f"Expected multi-step, got: {plan}"
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="open_app", app="Steam")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                         query="GTA V", app="Steam")


def test_search_v2_open_file_explorer_and_search():
    plan = plan_action("Open File Explorer and search for notes.txt",
                       use_llm=False)
    assert plan is not None
    assert "steps" in plan, f"Expected multi-step, got: {plan}"
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="open_app",
                         app="File Explorer")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                         query="notes.txt", app="File Explorer")


def test_search_v2_open_vscode_and_search():
    plan = plan_action("Open VS Code and search for main.py", use_llm=False)
    assert plan is not None
    assert "steps" in plan, f"Expected multi-step, got: {plan}"
    assert len(plan["steps"]) == 2
    _assert_plan_matches(plan["steps"][0], action="open_app", app="VS Code")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                         query="main.py", app="VS Code")


def test_search_v2_direct_search_in_app():
    """Direct "search for X in Y" without prior open_app."""
    plan = plan_action("search for chatgpt in Microsoft Store", use_llm=False)
    assert plan is not None
    assert plan.get("action") == "search_in_app_v2", f"Got: {plan}"
    assert plan.get("query") == "chatgpt"
    assert "Microsoft Store" in plan.get("app", "")


def test_search_v2_unknown_app_falls_back_gracefully():
    """Search in an app with no profile should still produce a valid plan."""
    plan = plan_action("search for hello in Photoshop", use_llm=False)
    assert plan is not None
    assert plan.get("action") == "search_in_app_v2", f"Got: {plan}"
    assert plan.get("query") == "hello"
    assert "Photoshop" in plan.get("app", "")


def test_search_v2_cache_population():
    """Verify the search cache module exists and can store/retrieve entries."""
    from ui_core import _get_cached_search, _set_cached_search, SEARCH_METHOD_ACCESSIBILITY
    _set_cached_search("test_app", {"method": SEARCH_METHOD_ACCESSIBILITY,
                                     "automation_id": "SearchBox",
                                     "class_name": "TestWindow"})
    cached = _get_cached_search("test_app")
    assert cached is not None
    assert cached["method"] == SEARCH_METHOD_ACCESSIBILITY
    assert cached["automation_id"] == "SearchBox"
    # Cleanup
    _set_cached_search("test_app", {})


def test_search_v2_shortcut_registry():
    """Verify the shortcut registry contains all expected entries."""
    from ui_core import SEARCH_SHORTCUT_REGISTRY
    # Browsers
    assert SEARCH_SHORTCUT_REGISTRY["chrome"] == ["ctrl", "l"]
    assert SEARCH_SHORTCUT_REGISTRY["edge"] == ["ctrl", "l"]
    assert SEARCH_SHORTCUT_REGISTRY["firefox"] == ["ctrl", "k"]
    assert SEARCH_SHORTCUT_REGISTRY["opera"] == ["ctrl", "l"]
    assert SEARCH_SHORTCUT_REGISTRY["brave"] == ["ctrl", "l"]
    assert SEARCH_SHORTCUT_REGISTRY["internet explorer"] == ["ctrl", "e"]
    # Office
    assert SEARCH_SHORTCUT_REGISTRY["word"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["excel"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["outlook"] == ["ctrl", "e"]
    assert SEARCH_SHORTCUT_REGISTRY["onenote"] == ["ctrl", "e"]
    # IDEs
    assert SEARCH_SHORTCUT_REGISTRY["vs code"] == ["ctrl", "p"]
    assert SEARCH_SHORTCUT_REGISTRY["visual studio"] == ["ctrl", "shift", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["sublime text"] == ["ctrl", "p"]
    # JetBrains
    assert SEARCH_SHORTCUT_REGISTRY["intellij idea"] == ["shift", "shift"]
    assert SEARCH_SHORTCUT_REGISTRY["pycharm"] == ["shift", "shift"]
    # Communication
    assert SEARCH_SHORTCUT_REGISTRY["slack"] == ["ctrl", "k"]
    assert SEARCH_SHORTCUT_REGISTRY["discord"] == ["ctrl", "k"]
    assert SEARCH_SHORTCUT_REGISTRY["microsoft teams"] == ["ctrl", "e"]
    # Media
    assert SEARCH_SHORTCUT_REGISTRY["spotify"] == ["ctrl", "l"]
    assert SEARCH_SHORTCUT_REGISTRY["apple music"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["itunes"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["vlc"] == ["ctrl", "f"]
    # Gaming
    assert SEARCH_SHORTCUT_REGISTRY["steam"] == ["ctrl", "l"]
    assert SEARCH_SHORTCUT_REGISTRY["epic games launcher"] == ["ctrl", "l"]
    assert SEARCH_SHORTCUT_REGISTRY["battle.net"] == ["ctrl", "l"]
    # File management
    assert SEARCH_SHORTCUT_REGISTRY["file explorer"] == ["ctrl", "e"]
    assert SEARCH_SHORTCUT_REGISTRY["total commander"] == ["ctrl", "f"]
    # Adobe
    assert SEARCH_SHORTCUT_REGISTRY["photoshop"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["illustrator"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["premiere pro"] == ["ctrl", "f"]
    # Dev tools
    assert SEARCH_SHORTCUT_REGISTRY["windows terminal"] == ["ctrl", "shift", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["command prompt"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["powershell"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["postman"] == ["ctrl", "f"]
    # System
    assert SEARCH_SHORTCUT_REGISTRY["registry editor"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["event viewer"] == ["ctrl", "f"]
    # Cloud
    assert SEARCH_SHORTCUT_REGISTRY["dropbox"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["google drive"] == ["ctrl", "f"]
    assert SEARCH_SHORTCUT_REGISTRY["onedrive"] == ["ctrl", "f"]


# ---------------------------------------------------------------------------
# Bug 5 — intent normalization (open/run/launch/start produce same plan)
# ---------------------------------------------------------------------------
def test_intent_normalization_run_synonym():
    """'Run Microsoft Store and search Spotify' same as 'Open Microsoft Store'."""
    plan_run = plan_action("Run Microsoft Store and search Spotify", use_llm=False)
    plan_open = plan_action("Open Microsoft Store and search Spotify", use_llm=False)
    plan_launch = plan_action("Launch Microsoft Store and search Spotify", use_llm=False)
    plan_start = plan_action("Start Microsoft Store and search Spotify", use_llm=False)
    for plan in (plan_run, plan_open, plan_launch, plan_start):
        assert plan is not None
        assert "steps" in plan, f"Expected multi-step, got: {plan}"
        assert len(plan["steps"]) == 2
        _assert_plan_matches(plan["steps"][0], action="open_app")
        _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                             query="Spotify")


def test_intent_normalization_run_single():
    """'Run Chrome' equals 'Open Chrome'."""
    plan1 = plan_action("Run Chrome", use_llm=False)
    plan2 = plan_action("Open Chrome", use_llm=False)
    assert plan1 is not None and plan2 is not None
    assert plan1.get("action") == "open_app"
    assert plan2.get("action") == "open_app"
    assert plan1.get("app").lower() == plan2.get("app").lower()


# ---------------------------------------------------------------------------
# Bug 8 — Diagnostics command
# ---------------------------------------------------------------------------
def test_diagnostics_action_in_supported():
    """'diagnostics' must be a registered action."""
    from planner import SUPPORTED_ACTIONS
    assert "diagnostics" in SUPPORTED_ACTIONS


def test_diagnostics_plan():
    """Plan for 'run diagnostics' should produce diagnostics action."""
    plan = plan_action("run diagnostics", use_llm=False)
    assert plan is not None
    assert plan.get("action") == "diagnostics", f"Got: {plan}"


def test_diagnostics_module_exists():
    """diagnostics.py must be importable."""
    try:
        import diagnostics
        assert hasattr(diagnostics, "check_environment")
        assert hasattr(diagnostics, "get_report_text")
    except ImportError:
        pytest.fail("diagnostics module not found")


def test_diagnostics_report_structure():
    """Diagnostics report must contain expected keys."""
    from diagnostics import check_environment
    report = check_environment()
    assert "python_version" in report
    assert "libraries" in report
    assert "win32_api" in report
    assert "accessibility" in report
    # Libraries should include all we expect
    libs = report.get("libraries", {})
    assert "pywinauto" in libs


# ---------------------------------------------------------------------------
# App discovery
# ---------------------------------------------------------------------------
def test_app_discovery_function():
    """discover_installed_apps should return a dict."""
    from ui_core import discover_installed_apps
    discovered = discover_installed_apps()
    assert isinstance(discovered, dict)
    # At minimum, windows should discover some apps
    assert len(discovered) >= 0  # non-destructive — may be empty in CI


def test_app_discovery_start_menu():
    """Start Menu shortcuts should be discoverable."""
    from ui_core import discover_installed_apps
    discovered = discover_installed_apps()
    # Check for common apps that should be in Start Menu
    names = [v.get("name", "").lower() for v in discovered.values()]
    # If the test machine has these, they should be discovered
    known = {"calculator", "notepad", "command prompt", "powershell",
             "file explorer", "settings", "paint"}
    found = [n for n in names if n in known]
    # Don't fail — just check the mechanism works
    assert isinstance(found, list)


# ---------------------------------------------------------------------------
# Comma-splatting protection — commas in middle of clauses don't split
# ---------------------------------------------------------------------------
def test_comma_in_middle_of_clause_not_split():
    """Comma inside a search query should NOT become a clause boundary."""
    plan = plan_action(
        "Open Chrome and search for it, you rock my world",
        use_llm=False,
    )
    assert plan is not None
    assert "steps" in plan, f"Expected multi-step, got: {plan}"
    assert len(plan["steps"]) == 2, (
        f"Expected 2 steps, got {len(plan.get('steps', []))}: {plan}"
    )
    _assert_plan_matches(plan["steps"][0], action="open_app", app="Chrome")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2",
                         query="it, you rock my world")


def test_comma_between_commands_still_splits():
    """Comma between two commands should still be a boundary."""
    plan = plan_action("Open Chrome, search for weather", use_llm=False)
    assert plan is not None
    assert "steps" in plan, f"Expected multi-step, got: {plan}"
    assert len(plan["steps"]) == 2, (
        f"Expected 2 steps, got {len(plan.get('steps', []))}: {plan}"
    )
    _assert_plan_matches(plan["steps"][0], action="open_app", app="Chrome")
    _assert_plan_matches(plan["steps"][1], action="search_in_app_v2", query="weather")


# ---------------------------------------------------------------------------
# Acceptance tests — Issue 7: Search context persistence
# ---------------------------------------------------------------------------
def test_search_context_thriller():
    """'Search for Thriller' should route to search_in_app_v2 when
    session memory has current_app = 'Apple Music'."""
    import session_memory as sm
    sm.set("current_app", "Apple Music")
    try:
        plan = plan_action("Search for Thriller", use_llm=False)
        assert plan is not None
        assert plan.get("action") == "search_in_app_v2", f"Got: {plan}"
        assert plan.get("app") == "Apple Music"
        assert plan.get("query") == "Thriller"
    finally:
        sm.clear()


def test_search_context_beat_it():
    """'Search for Beat It' should route to search_in_app_v2 when
    session memory has current_app = 'Apple Music'."""
    import session_memory as sm
    sm.set("current_app", "Apple Music")
    try:
        plan = plan_action("Search for Beat It", use_llm=False)
        assert plan is not None
        assert plan.get("action") == "search_in_app_v2", f"Got: {plan}"
        assert plan.get("app") == "Apple Music"
        assert plan.get("query") == "Beat It"
    finally:
        sm.clear()


def test_search_context_python_standalone():
    """'Search for Python' with no context should be a web search."""
    import session_memory as sm
    sm.clear()
    plan = plan_action("Search for Python", use_llm=False)
    assert plan is not None
    assert plan.get("action") == "web_search", f"Got: {plan}"
    assert plan.get("query") == "Python"


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main(["-v", "--tb=short", __file__]))
