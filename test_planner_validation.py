"""
test_planner_validation.py
--------------------------
Planner routing validation tests.
Tests the fast-path routing without calling LLM.
"""

import sys

from planner import plan_action, SUPPORTED_ACTIONS, _FAST_PATH_TRIGGERS

PASS = 0
FAIL = 0


def test(label: str, user_input: str, expected: dict):
    global PASS, FAIL
    plan = plan_action(user_input, use_llm=False)
    status = "PASS" if plan == expected else "FAIL"
    if status == "PASS":
        PASS += 1
    else:
        FAIL += 1
    print(f"\nINPUT:    {user_input}")
    print(f"PLAN:     {plan}")
    print(f"EXPECTED: {expected}")
    print(f"STATUS:   {status}")


print("=" * 60)
print("PLANNER VALIDATION TESTS")
print("=" * 60)

# =====================================================================
# MULTI-STEP COMMANDS
# =====================================================================
print("\n--- Multi-step: 2-action chains ---")

test(
    "Open calculator, create reminder in 5 minutes",
    "Open calculator, create reminder in 5 minutes",
    {"steps": [
        {"action": "open_app", "app": "calculator"},
        {"action": "ai_chat", "text": "create reminder in 5 minutes"},
    ]},
)

test(
    "Open calculator and open notepad",
    "Open calculator and open notepad",
    {"steps": [
        {"action": "open_app", "app": "calculator"},
        {"action": "open_app", "app": "notepad"},
    ]},
)

test(
    "Open calculator and remind me in 2 minutes to stop studying",
    "Open calculator and remind me in 2 minutes to stop studying",
    {"steps": [
        {"action": "open_app", "app": "calculator"},
        {"action": "reminder", "time": "in 2 minutes", "task": "stop studying"},
    ]},
)

test(
    "Open chrome and search for AI",
    "Open chrome and search for AI",
    {"steps": [
        {"action": "open_app", "app": "chrome"},
        {"action": "search_in_app", "query": "AI", "app": "chrome"},
    ]},
)

test(
    "Open vs code then open terminal",
    "Open vs code then open terminal",
    {"steps": [
        {"action": "open_app", "app": "vs code"},
        {"action": "open_app", "app": "terminal"},
    ]},
)

test(
    "Open calculator after that set a reminder",
    "Open calculator after that set a reminder",
    {"steps": [
        {"action": "open_app", "app": "calculator"},
        {"action": "ai_chat", "text": "set a reminder"},
    ]},
)

test(
    "Open browser also open notepad",
    "Open browser also open notepad",
    {"steps": [
        {"action": "open_app", "app": "browser"},
        {"action": "open_app", "app": "notepad"},
    ]},
)

test(
    "Open calculator plus open calendar",
    "Open calculator plus open calendar",
    {"steps": [
        {"action": "open_app", "app": "calculator"},
        {"action": "open_app", "app": "calendar"},
    ]},
)

test(
    "Search Laplace Transform and save to file",
    "Search Laplace Transform and save to file",
    {"steps": [
        {"action": "web_search", "query": "Laplace Transform"},
        {"action": "ai_chat", "text": "save to file"},
    ]},
)

print("\n--- Multi-step: 5-action chain ---")

test(
    "Search Laplace Transform, save notes, open VS Code, open notes file, create reminder in 5 minutes",
    "Search Laplace Transform, save notes, open VS Code, open notes file, create reminder in 5 minutes",
    {"steps": [
        {"action": "web_search", "query": "Laplace Transform"},
        {"action": "ai_chat", "text": "save notes"},
        {"action": "open_app", "app": "VS Code"},
        {"action": "open_app", "app": "notes file"},
        {"action": "ai_chat", "text": "create reminder in 5 minutes"},
    ]},
)

print("\n--- Multi-step: pronoun resolution ---")

test(
    "Create folder Test, create file notes.txt, write hello world into it",
    "Create folder Test, create file notes.txt, write hello world into it",
    {"steps": [
        {"action": "folder_operation", "op": "create_folder", "name": "Test"},
        {"action": "file_operation", "op": "create_file", "name": "notes.txt"},
        {"action": "file_operation", "op": "write_file", "path": "Test/notes.txt", "content": "hello world"},
    ]},
)

print("\n--- Multi-step: then + comma ---")

test(
    "Open Spotify, set volume to 40, create reminder in 10 minutes, then remember that I was listening to music",
    "Open Spotify, set volume to 40, create reminder in 10 minutes, then remember that I was listening to music",
    {"steps": [
        {"action": "open_app", "app": "Spotify"},
        {"action": "volume_control", "op": "set", "level": 40},
        {"action": "ai_chat", "text": "create reminder in 10 minutes"},
        {"action": "memory_store", "fact": "I was listening to music"},
    ]},
)

print("\n--- Multi-step: context carry-over ---")

test(
    "Open downloads, create folder Test, create file notes.txt, write hello world into it",
    "Open downloads, create folder Test, create file notes.txt, write hello world into it",
    {"steps": [
        {"action": "pc_control", "phrase": "open downloads"},
        {"action": "folder_operation", "op": "create_folder", "name": "Test"},
        {"action": "file_operation", "op": "create_file", "name": "notes.txt"},
        {"action": "file_operation", "op": "write_file", "path": "Test/notes.txt", "content": "hello world"},
    ]},
)

# =====================================================================
# SINGLE-ACTION TESTS (unchanged below)
# =====================================================================
# Simple open_app should still work
print("\n--- Single-action: open_app ---")

test(
    "Open calculator",
    "Open calculator",
    {"action": "open_app", "app": "calculator"},
)

test(
    "Open VS Code",
    "Open VS Code",
    {"action": "open_app", "app": "VS Code"},
)

test(
    "Create file notes.txt",
    "Create file notes.txt",
    {"action": "file_operation", "op": "create_file", "name": "notes.txt"},
)

test(
    "Open Visual Studio Code",
    "Open Visual Studio Code",
    {"action": "open_app", "app": "Visual Studio Code"},
)

test(
    "Launch Chrome",
    "Launch Chrome",
    {"action": "open_app", "app": "Chrome"},
)

test(
    "Start Notepad",
    "Start Notepad",
    {"action": "open_app", "app": "Notepad"},
)

# --- Clipboard priority ---
print("\n--- Single-action: clipboard ---")

test(
    "Read my clipboard",
    "Read my clipboard",
    {"action": "clipboard", "op": "read"},
)

test(
    "Read clipboard",
    "Read clipboard",
    {"action": "clipboard", "op": "read"},
)

test(
    "Read the clipboard",
    "Read the clipboard",
    {"action": "clipboard", "op": "read"},
)

test(
    "What's on my clipboard",
    "What's on my clipboard",
    {"action": "clipboard", "op": "read"},
)

test(
    "What is on the clipboard",
    "What is on the clipboard",
    {"action": "clipboard", "op": "read"},
)

# --- PC control priority ---
print("\n--- Single-action: PC control ---")

test(
    "Open downloads",
    "Open downloads",
    {"action": "pc_control", "phrase": "open downloads"},
)

test(
    "Open task manager",
    "Open task manager",
    {"action": "pc_control", "phrase": "open task manager"},
)

test(
    "Open control panel",
    "Open control panel",
    {"action": "pc_control", "phrase": "open control panel"},
)

test(
    "Open settings",
    "Open settings",
    {"action": "pc_control", "phrase": "open settings"},
)

test(
    "Lock computer",
    "Lock computer",
    {"action": "pc_control", "phrase": "lock computer"},
)

# --- File operations ---
print("\n--- Single-action: file operations ---")

test(
    "Read file notes.txt",
    "Read file notes.txt",
    {"action": "file_operation", "op": "read_file", "path": "notes.txt"},
)

test(
    "Create a test.txt",
    "Create a test.txt",
    {"action": "file_operation", "op": "create_file", "name": "test.txt"},
)

test(
    "Search for tax documents in files",
    "Search for tax documents in files",
    {"action": "file_operation", "op": "search_files", "query": "tax Documents"},
)

test(
    "Create folder TestFolder",
    "Create folder TestFolder",
    {"action": "folder_operation", "op": "create_folder", "name": "TestFolder"},
)

test(
    "Open file report.pdf",
    "Open file report.pdf",
    {"action": "file_operation", "op": "open_file", "path": "report.pdf"},
)

# --- System commands ---
print("\n--- Single-action: system commands ---")

test(
    "What time is it",
    "What time is it",
    {"action": "time"},
)

test(
    "What's today's date",
    "What's today's date",
    {"action": "date"},
)

test(
    "Screenshot",
    "Screenshot",
    {"action": "screenshot"},
)

test(
    "Volume up",
    "Volume up",
    {"action": "volume_control", "op": "up"},
)

test(
    "Set volume to 50",
    "Set volume to 50",
    {"action": "volume_control", "op": "set", "level": 50},
)

# =====================================================================
# NEW ACTION TYPE TESTS
# =====================================================================
print("\n--- New actions: close_app ---")

test(
    "Close notepad",
    "Close notepad",
    {"action": "close_app", "app": "notepad"},
)

test(
    "Close chrome",
    "Close chrome",
    {"action": "close_app", "app": "chrome"},
)

print("\n--- New actions: switch_window ---")

test(
    "Switch to chrome",
    "Switch to chrome",
    {"action": "switch_window", "target": "chrome"},
)

test(
    "Switch to Visual Studio Code",
    "Switch to Visual Studio Code",
    {"action": "switch_window", "target": "Visual Studio Code"},
)

print("\n--- New actions: open_folder ---")

test(
    "Open folder C:/Users/test",
    "Open folder C:/Users/test",
    {"action": "open_folder", "path": "C:/Users/test"},
)

print("\n--- New actions: rename_folder ---")

test(
    "Rename folder old_name to new_name",
    "Rename folder old_name to new_name",
    {"action": "folder_operation", "op": "rename_folder",
     "path": "old_name", "new_name": "new_name"},
)

print("\n--- New actions: append_file ---")

test(
    "Append hello world to notes.txt",
    "Append hello world to notes.txt",
    {"action": "file_operation", "op": "append_file",
     "path": "notes.txt", "content": "hello world"},
)

print("\n--- New actions: search_in_app ---")

test(
    "Search for error in code editor",
    "Search for error in code editor",
    {"action": "search_in_app", "query": "error", "app": "code editor"},
)

print("\n--- New actions: type_text ---")

test(
    "Type hello world",
    "Type hello world",
    {"action": "type_text", "text": "hello world"},
)

print("\n--- New actions: press_key ---")

test(
    "Press enter",
    "Press enter",
    {"action": "press_key", "key": "enter"},
)

test(
    "Press ctrl s",
    "Press ctrl s",
    {"action": "press_key", "key": "ctrl s"},
)

print("\n--- New actions: scroll ---")

test(
    "Scroll down",
    "Scroll down",
    {"action": "scroll", "direction": "down", "amount": 3},
)

test(
    "Scroll up 5",
    "Scroll up 5",
    {"action": "scroll", "direction": "up", "amount": 5},
)

print("\n--- New actions: browser_open ---")

test(
    "Go to https://google.com",
    "Go to https://google.com",
    {"action": "browser_open", "url": "https://google.com"},
)

print("\n--- New actions: browser_search ---")

test(
    "Search in browser for AI news",
    "Search in browser for AI news",
    {"action": "browser_search", "query": "AI news"},
)

print("\n--- New actions: run_program ---")

test(
    "Run notepad.exe",
    "Run notepad.exe",
    {"action": "run_program", "program": "notepad.exe"},
)

print("\n--- New actions: run_terminal_command ---")

test(
    "Run command dir",
    "Run command dir",
    {"action": "run_terminal_command", "command": "dir"},
)

test(
    "Execute echo hello",
    "Execute echo hello",
    {"action": "run_terminal_command", "command": "echo hello"},
)

print("\n--- New actions: generate_code ---")

test(
    "Generate code for a fibonacci function",
    "Generate code for a fibonacci function",
    {"action": "generate_code", "description": "a fibonacci function"},
)

print("\n--- New actions: wait ---")

test(
    "Wait 5 seconds",
    "Wait 5 seconds",
    {"action": "wait", "seconds": 5},
)

test(
    "Wait for 10 seconds",
    "Wait for 10 seconds",
    {"action": "wait", "seconds": 10},
)

print("\n--- New actions: multi-step with new verbs ---")

test(
    "Type hello world and press enter",
    "Type hello world and press enter",
    {"steps": [
        {"action": "type_text", "text": "hello world"},
        {"action": "press_key", "key": "enter"},
    ]},
)

test(
    "Press ctrl s then switch to chrome",
    "Press ctrl s then switch to chrome",
    {"steps": [
        {"action": "press_key", "key": "ctrl s"},
        {"action": "switch_window", "target": "chrome"},
    ]},
)

test(
    "Close notepad and open chrome",
    "Close notepad and open chrome",
    {"steps": [
        {"action": "close_app", "app": "notepad"},
        {"action": "open_app", "app": "chrome"},
    ]},
)

# --- Summary ---
print("\n" + "=" * 60)
print(f"RESULTS:  {PASS} passed, {FAIL} failed out of {PASS + FAIL}")
print("=" * 60)

if FAIL > 0:
    sys.exit(1)
