"""Adapters bridging legacy handler implementations to the new execution engine.

Wraps existing functions from task_executor.py and related modules as
TaskHandler instances, enabling gradual migration to DAG-based execution.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
import webbrowser
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from jarvis.interfaces.executor import TaskHandler
from jarvis.types import ExecutionGraph, TaskNode

logger = logging.getLogger("jarvis.execution.adapter")


class LegacyHandlerAdapter(TaskHandler):
    """Wraps a legacy handler function as a TaskHandler."""

    def __init__(self, action: str, handler_fn: Callable[[TaskNode, dict], str]) -> None:
        self._action = action
        self._handler_fn = handler_fn

    @property
    def action(self) -> str:
        return self._action

    def execute(self, task: TaskNode, context: dict) -> str:
        return self._handler_fn(task, context)


# Context for legacy executors
_EXECUTOR_CONTEXT: dict = {"speak": None, "apps": [], "chat": None, "memory": None, "settings": None}


def set_executor_context(ctx: dict) -> None:
    _EXECUTOR_CONTEXT.update(ctx)


def get_executor_context() -> dict:
    return dict(_EXECUTOR_CONTEXT)


# Plan bridge
def quick_plan(text: str) -> Optional[dict]:
    try:
        import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        from planner import plan_action
        return plan_action(text)
    except Exception as exc:
        logger.warning("quick_plan failed: %s", exc)
        return None


def execute_via_engine(engine, plan: dict, user_text: str = "") -> str:
    if engine is None:
        return _fallback_execute(plan)
    graph = _plan_to_graph(plan)
    if graph is None:
        return _fallback_execute(plan)
    result = engine.execute(graph)
    outputs = [tr.output for tr in result.task_results.values() if tr.output]
    return " ".join(outputs) if outputs else "Task completed, sir."


def _plan_to_graph(plan: dict) -> Optional[ExecutionGraph]:
    if not isinstance(plan, dict):
        return None
    graph = ExecutionGraph(id=f"plan_{int(time.time())}")
    if "steps" in plan:
        for i, step in enumerate(plan["steps"]):
            action = step.get("action", "unknown")
            params = {k: v for k, v in step.items() if k != "action"}
            node = TaskNode(id=f"step_{i}", action=action, params=params, depends_on=[f"step_{i-1}"] if i > 0 else [])
            graph.add_node(node)
    else:
        action = plan.get("action", "ai_chat")
        params = {k: v for k, v in plan.items() if k != "action"}
        graph.add_node(TaskNode(id="step_0", action=action, params=params))
    return graph


def _fallback_execute(plan: dict) -> str:
    try:
        import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        from planner import _dispatch
        return _dispatch(plan)
    except Exception as exc:
        return f"Execution failed: {exc}"


# Handler implementations
def _handle_open_app(task: TaskNode, context: dict) -> str:
    from app_launcher import app_launcher
    apps = _EXECUTOR_CONTEXT.get("apps", [])
    raw = (task.params.get("app") or "").strip().lower().replace(".", "")
    if not raw:
        return "No app specified."
    ALIAS_MAP = {"vs code": "Visual Studio Code", "vscode": "Visual Studio Code", "code": "Visual Studio Code",
                 "chrome": "Google Chrome", "edge": "Microsoft Edge", "spotify": "Spotify",
                 "terminal": "Terminal", "cmd": "Command Prompt", "notepad": "Notepad", "calculator": "Calculator"}
    resolved = ALIAS_MAP.get(raw, raw)
    best_score, best_app = 0, None
    for app in apps:
        name = app["Name"].lower()
        score = 100 if raw == name else 80 if all(w in name for w in raw.split()) else 70 if name.startswith(raw) else 50 if raw in name else 0
        if score > best_score:
            best_score, best_app = score, app
    if best_app and best_score >= 60:
        try:
            r = app_launcher.launch_and_verify(best_app["Name"])
            if r.status.value == "success":
                return f"Opening {best_app['Name']}, sir."
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{best_app['AppID']}"])
            return f"Opening {best_app['Name']}, sir."
        except Exception:
            return "Failed to launch."
    try:
        fn = resolved or task.params.get("app", "")
        if fn:
            r = app_launcher.launch_and_verify(fn)
            if r.status.value == "success":
                return f"Opening {fn}."
            clean_app = re.sub(r'[^a-zA-Z0-9_\-]', '', fn)
            subprocess.Popen(["cmd.exe", "/c", "start", "", clean_app], shell=False)
            return f"Opening {fn}."
    except Exception:
        pass
    return "App not found."


def _handle_web_search(task: TaskNode, context: dict) -> str:
    import urllib.parse, urllib.request, html
    q = (task.params.get("query") or task.params.get("q") or task.params.get("text") or task.params.get("search") or "").strip()
    if not q:
        return "No query provided, sir."
    try:
        d = urllib.parse.urlencode({"q": q}).encode()
        req = urllib.request.Request("https://lite.duckduckgo.com/lite/", data=d, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            p = r.read().decode("utf-8")
        snippets = [html.unescape(re.sub(r"<[^>]+>", "", s)).strip() for s in re.findall(r"class=[\x22\x27]result-snippet[\x22\x27][^>]*>(.*?)</", p, re.DOTALL)][:4]
        if not snippets:
            return "No results."
        chat = _EXECUTOR_CONTEXT.get("chat")
        return chat(f"User asked: {q}. Answer from: {' '.join(snippets)}") if chat else snippets[0]
    except Exception as e:
        return f"Search failed: {e}"


def _handle_time(task: TaskNode, context: dict) -> str:
    return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


def _handle_date(task: TaskNode, context: dict) -> str:
    return f"Today is {datetime.now().strftime('%d %B %Y')}, sir."


def _handle_file_operation(task: TaskNode, context: dict) -> str:
    import file_manager
    op = (task.params.get("op") or "").strip()
    if not op:
        return "No operation."
    allowed = {"name", "path", "query", "dest_folder", "new_name", "content", "folder"}
    params = {k: v for k, v in task.params.items() if k in allowed and v is not None}
    return file_manager.run(op, **params).get("tts") or "File operation done."


def _handle_folder_operation(task: TaskNode, context: dict) -> str:
    import file_manager
    op = (task.params.get("op") or "").strip()
    if not op:
        return "No operation."
    allowed = {"name", "path", "parent"}
    params = {k: v for k, v in task.params.items() if k in allowed and v is not None}
    return file_manager.run(op, **params).get("tts") or "Folder operation done."


def _handle_reminder(task: TaskNode, context: dict) -> str:
    from reminders import add_reminder, list_reminders, remove_reminder, clear_reminders
    op = (task.params.get("op") or "add").lower()
    if op == "list":
        items = list_reminders()
        return "You have no reminders, sir." if not items else "Your reminders, sir: " + "; ".join(f"{i+1}. {r['task']}" for i, r in enumerate(items))
    if op == "clear":
        return f"Cleared {clear_reminders()} reminders, sir."
    if op == "remove":
        return "Reminder deleted, sir." if remove_reminder(int(task.params.get("index", 0)) - 1) else "Reminder not found, sir."
    r = add_reminder(task.params.get("time", ""), task.params.get("task", ""))
    return f"Reminder set for {r.get('human_time', '?')}, sir."


def _handle_clipboard(task: TaskNode, context: dict) -> str:
    import clipboard_tools
    op = (task.params.get("op") or "read").lower()
    if op == "read":
        t = clipboard_tools.read()
        return f"Clipboard contents, sir: {t[:400]}" if t else "The clipboard is empty, sir."
    if op == "write":
        clipboard_tools.write(task.params.get("text", ""))
        return "Copied to clipboard, sir."
    if op == "clear":
        clipboard_tools.clear()
        return "Clipboard cleared, sir."
    return "Done, sir."


def _handle_screenshot(task: TaskNode, context: dict) -> str:
    try:
        import mss
        os.makedirs("Screenshots", exist_ok=True)
        p = f"Screenshots/shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        with mss.MSS() as s:
            s.shot(output=p)
        return f"Screenshot captured, sir."
    except Exception as e:
        return f"Screenshot failed, sir: {e}"


def _handle_volume_control(task: TaskNode, context: dict) -> str:
    op = (task.params.get("op") or "").lower()
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        v = AudioUtilities.GetSpeakers().EndpointVolume
        if op == "up":
            v.SetMasterVolumeLevelScalar(min(v.GetMasterVolumeLevelScalar() + 0.1, 1.0), None)
            return "Volume increased, sir."
        if op == "down":
            v.SetMasterVolumeLevelScalar(max(v.GetMasterVolumeLevelScalar() - 0.1, 0.0), None)
            return "Volume decreased, sir."
        if op == "mute":
            v.SetMute(1, None); return "Muted, sir."
        if op == "unmute":
            v.SetMute(0, None); return "Unmuted, sir."
        if op == "set":
            v.SetMasterVolumeLevelScalar(max(0, min(int(task.params.get("level", 50)), 100)) / 100, None)
            return f"Volume set to {task.params.get('level')}%, sir."
    except Exception as exc:
        logger.warning("Volume command failed: %s", exc)
    return "Volume command failed, sir."


def _handle_system_control(task: TaskNode, context: dict) -> str:
    op = (task.params.get("op") or "").lower()
    if "lock" in op:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], capture_output=True, timeout=5); return "Locking the workstation, sir."
    if "shutdown" in op:
        subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True, timeout=5); return "Shutting down in 5 seconds, sir."
    if "restart" in op:
        subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True, timeout=5); return "Restarting in 5 seconds, sir."
    return "Unknown system command, sir."


def _handle_pc_control(task: TaskNode, context: dict) -> str:
    return _handle_system_control(task, context)


def _handle_close_app(task: TaskNode, context: dict) -> str:
    app = re.sub(r'[^a-zA-Z0-9_.-]', '', (task.params.get("app") or "").strip())
    if not app:
        return "No application specified, sir."
    try:
        subprocess.run(["taskkill", "/IM", app + ".exe", "/F"], capture_output=True, text=True, timeout=5)
        return f"Closed {app}, sir."
    except Exception as e:
        return f"Failed to close {app}, sir: {e}"


def _handle_ai_chat(task: TaskNode, context: dict) -> str:
    chat = _EXECUTOR_CONTEXT.get("chat")
    t = task.params.get("text", "")
    return chat(t) if chat and t else "Ready."


def _handle_browser_open(task: TaskNode, context: dict) -> str:
    url = (task.params.get("url") or "").strip()
    if not url:
        return "No URL provided, sir."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        webbrowser.open(url); return f"Opening {url}, sir."
    except Exception as e:
        return f"Failed to open the browser, sir: {e}"


def _handle_browser_search(task: TaskNode, context: dict) -> str:
    import urllib.parse
    q = (task.params.get("query") or task.params.get("q") or task.params.get("text") or task.params.get("search") or "").strip()
    if q:
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(q)}")
        return f"Searching for {q}, sir."
    return "No query provided, sir."


def _handle_click(task: TaskNode, context: dict) -> str:
    from ui_core import automator
    return automator.click(x=task.params.get("x"), y=task.params.get("y"), button=task.params.get("button", "left"))


def _handle_double_click(task: TaskNode, context: dict) -> str:
    from ui_core import automator
    return automator.double_click(x=task.params.get("x"), y=task.params.get("y"))


def _handle_right_click(task: TaskNode, context: dict) -> str:
    from ui_core import automator
    return automator.right_click(x=task.params.get("x"), y=task.params.get("y"))


def _handle_type_text(task: TaskNode, context: dict) -> str:
    from ui_core import automator
    return automator.type_text((task.params.get("text") or "").strip())


def _handle_press_key(task: TaskNode, context: dict) -> str:
    from ui_core import automator
    return automator.press_key((task.params.get("key") or "").strip())


def _handle_scroll(task: TaskNode, context: dict) -> str:
    from ui_core import automator
    return automator.scroll(direction=task.params.get("direction", "down"), amount=int(task.params.get("amount", 3)))


def _handle_music(task: TaskNode, context: dict) -> str:
    import keyboard
    op = (task.params.get("op") or "").lower()
    if op in ("play", "pause"): keyboard.send("play/pause media"); return "Toggled playback, sir."
    if op in ("next", "skip"): keyboard.send("next track"); return "Skipping to the next track, sir."
    if op == "previous": keyboard.send("previous track"); return "Going back a track, sir."
    return "Unknown music command, sir."


def _handle_memory_store(task: TaskNode, context: dict) -> str:
    fact = (task.params.get("fact") or "").strip()
    mem = _EXECUTOR_CONTEXT.get("memory")
    if not fact or not mem:
        return "Memory is unavailable, sir."
    d = mem.load(); d.setdefault("facts", []).append(fact); mem.save(d)
    return "Noted, sir. I'll remember that."


def _handle_memory_recall(task: TaskNode, context: dict) -> str:
    mem = _EXECUTOR_CONTEXT.get("memory")
    if not mem:
        return "Memory is unavailable, sir."
    facts = mem.load().get("facts", [])
    return "I have no stored facts, sir." if not facts else "What I remember, sir: " + "; ".join(facts)


def _handle_memory_clear(task: TaskNode, context: dict) -> str:
    mem = _EXECUTOR_CONTEXT.get("memory")
    if not mem:
        return "Memory is unavailable, sir."
    mem.save({"facts": []}); return "Memory cleared, sir."


def _handle_terminal(task: TaskNode, context: dict) -> str:
    cmd = (task.params.get("command") or "").strip()
    if not cmd or len(cmd) > 512 or not re.match(r"^[\w\s\-.:\\/@]+$", cmd):
        return "That command is invalid, sir."
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=15)
        o = (r.stdout or "").strip()[:400]
        return f"Done, sir. {o}" if o else "Done, sir."
    except subprocess.TimeoutExpired:
        return "The command timed out, sir."
    except Exception as e:
        return f"Command failed, sir: {e}"


def _handle_screen(task: TaskNode, context: dict) -> str:
    import mss
    op = task.params.get("op", "describe")
    prompts = {
        "describe": "Describe everything currently visible on this screen in detail. If there are any errors or issues shown, point them out.",
        "error": "Look closely at this screen capture. What error messages, tracebacks, or warning dialogs are visible?",
        "code_review": "Review the source code visible on this screen and highlight any bugs, typos, or syntax errors.",
        "summarize_document": "Summarize the primary document or text content visible on this screen.",
    }
    try:
        os.makedirs("Screenshots", exist_ok=True)
        p = f"Screenshots/s_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        with mss.MSS() as s:
            s.shot(output=p)
        from jarvis.planner.llm import _get_client
        client = _get_client()
        r = client.chat(model="qwen2.5vl:3b", messages=[{"role": "user", "content": prompts.get(op, prompts["describe"]), "images": [p]}])
        return r["message"]["content"]
    except Exception as e:
        logger.warning("Screen analysis failed: %s", e)
        return f"Screen analysis is unavailable, sir. Make sure Ollama vision model 'qwen2.5vl:3b' is installed."


def _handle_system_stats(task: TaskNode, context: dict) -> str:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        return f"CPU utilization is at {cpu}%, and RAM usage is at {mem}%, sir."
    except Exception:
        return "System statistics are currently unavailable, sir."


def _handle_wait(task: TaskNode, context: dict) -> str:
    try:
        seconds = float(task.params.get("seconds", 1.0))
        time.sleep(min(seconds, 10.0))
        return f"Certainly, sir. Paused for {seconds} seconds."
    except Exception:
        return "Done, sir."


def _handle_not_supported(task: TaskNode, context: dict) -> str:
    return "This feature is not currently available, sir."


# Registry
ADAPTER_ACTIONS: Dict[str, Callable[[TaskNode, dict], str]] = {
    "open_app": _handle_open_app, "close_app": _handle_close_app,
    "web_search": _handle_web_search, "time": _handle_time, "date": _handle_date,
    "file_operation": _handle_file_operation, "folder_operation": _handle_folder_operation,
    "reminder": _handle_reminder, "set_reminder": _handle_reminder,
    "clipboard": _handle_clipboard, "screenshot": _handle_screenshot,
    "volume_control": _handle_volume_control, "system_control": _handle_system_control,
    "pc_control": _handle_pc_control,
    "memory_store": _handle_memory_store, "memory_recall": _handle_memory_recall, "memory_clear": _handle_memory_clear,
    "ai_chat": _handle_ai_chat, "browser_open": _handle_browser_open, "browser_search": _handle_browser_search,
    "click": _handle_click, "double_click": _handle_double_click, "right_click": _handle_right_click,
    "type_text": _handle_type_text, "press_key": _handle_press_key, "scroll": _handle_scroll,
    "music": _handle_music, "run_terminal_command": _handle_terminal, "screen_awareness": _handle_screen,
    "system_stats": _handle_system_stats, "diagnostics": _handle_system_stats, "search_in_app_v2": _handle_web_search,
    "focus_window": _handle_not_supported, "hotkey": _handle_type_text, "wait": _handle_wait,
    "wait_for_window": _handle_wait, "generate_code": _handle_ai_chat, "run_program": _handle_open_app,
    "browser_click": _handle_web_search, "open_folder": _handle_file_operation,
    "move_mouse": _handle_type_text, "wait_for_element": _handle_wait, "calendar_event": _handle_not_supported,
    "email": _handle_not_supported, "whatsapp": _handle_not_supported,
}

