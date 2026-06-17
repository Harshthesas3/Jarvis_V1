"""
task_executor.py
----------------
Execute plans emitted by planner.py. Dispatches each step to the
appropriate tool module and returns a short, TTS-friendly string.

UPDATED: Integrated with production-grade search_agent that uses
prioritized fallback methods (Accessibility -> Automation ID -> OCR -> 
Keyboard -> Vision) with window validation.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
import webbrowser
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from planner import register_tool

logger = logging.getLogger("jarvis.executor")

# ---------------------------------------------------------------------------
# Context object — bundling shared dependencies that the executor needs but
# that the planner should not know about (TTS, screen awareness, the apps
# list, the contact book, the reminder engine, etc.).
# ---------------------------------------------------------------------------
ExecutorContext = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helper: screen awareness
# ---------------------------------------------------------------------------
def _capture_screen(folder: str = "Screenshots") -> Optional[str]:
    try:
        import mss
        os.makedirs(folder, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(folder, f"screenshot_{ts}.png")
        with mss.MSS() as sct:
            sct.shot(output=path)
        return path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Screenshot failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Handler builders — one per action. Each takes the plan dict + context and
# returns a TTS-friendly string.
# ---------------------------------------------------------------------------
def _handle_open_app(plan: dict, ctx: ExecutorContext) -> str:
    """Open an application with verification using app_launcher."""
    from app_launcher import app_launcher
    
    apps = ctx.get("apps", [])
    raw = (plan.get("app") or "").strip().lower().replace(".", "")
    if not raw:
        return "I did not catch the application name, sir."
    
    ALIAS_MAP = {
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "code": "Visual Studio Code",
        "android studio": "Android Studio",
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "edge": "Microsoft Edge",
        "microsoft edge": "Microsoft Edge",
        "apple music": "Apple Music",
        "spotify": "Spotify",
        "word": "Word",
        "excel": "Excel",
        "powerpoint": "PowerPoint",
        "outlook": "Outlook",
        "teams": "Microsoft Teams",
        "terminal": "Terminal",
        "cmd": "Command Prompt",
        "command prompt": "Command Prompt",
        "powershell": "Windows PowerShell",
        "notepad": "Notepad",
        "paint": "Paint",
        "calculator": "Calculator",
        "file explorer": "File Explorer",
        "explorer": "File Explorer",
        "task manager": "Task Manager",
        "control panel": "Control Panel",
        "settings": "Settings",
        "microsoft store": "Microsoft Store",
        "store": "Microsoft Store",
    }
    resolved = ALIAS_MAP.get(raw)
    if resolved:
        raw = resolved.lower()

    # Confidence-based matching
    best_score = 0
    best_app = None
    for app in apps:
        app_name = app["Name"].lower()
        raw_words = raw.split()
        if raw == app_name:
            score = 100
        elif all(w in app_name for w in raw_words):
            if any(raw == w or raw.startswith(w) for w in app_name.split()):
                score = 90
            else:
                score = 70
        elif app_name.startswith(raw):
            score = 80
        elif raw in app_name:
            score = 60
        else:
            score = 0
        if score > best_score:
            best_score = score
            best_app = app

    if best_app and best_score >= 60:
        try:
            # Use app_launcher for verified launch
            result = app_launcher.launch_and_verify(best_app["Name"])
            
            if result.status.value == "success":
                return f"Opening {best_app['Name']}, sir."
            else:
                logger.warning(f"Launch failed: {result.message}")
                # Fallback to old method
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{best_app['AppID']}"])
                return f"Opening {best_app['Name']}, sir."
        except Exception as exc:
            logger.warning("Launch failed: %s", exc)
            return "Failed to launch application, sir."
    
    # Try web fallbacks
    web_map = {
        "youtube": "https://youtube.com",
        "gmail": "https://mail.google.com",
        "whatsapp": "https://web.whatsapp.com",
        "chat gpt": "https://chatgpt.com",
        "chatgpt": "https://chatgpt.com",
        "google": "https://google.com",
    }
    for key, url in web_map.items():
        if key in raw:
            webbrowser.open(url)
            return f"Opening {key.title()}, sir."
    
    # Fallback: try launching via start command
    try:
        fallback_name = resolved or plan.get("app", "")
        if fallback_name:
            result = app_launcher.launch_and_verify(fallback_name)
            if result.status.value == "success":
                return f"Opening {fallback_name}, sir."
            subprocess.Popen(["start", "", fallback_name], shell=True)
            return f"Opening {fallback_name}, sir."
    except Exception as exc:
        logger.warning("Fallback launch failed: %s", exc)
    
    return "Application not found, sir."


def _handle_web_search(plan: dict, ctx: ExecutorContext) -> str:
    import urllib.parse
    import urllib.request
    import re
    import html

    query = (plan.get("query") or "").strip()
    if not query:
        return "I could not determine the search query, sir."
    speak = ctx.get("speak")
    if speak:
        speak(f"Searching the web for {query}, sir.")
    try:
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            "https://lite.duckduckgo.com/lite/",
            data=data,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            page = resp.read().decode("utf-8")
        raw_snippets = re.findall(
            r"class=[\x22\x27]result-snippet[\x22\x27][^>]*>(.*?)</",
            page, re.DOTALL,
        )
        cleaned = []
        for s in raw_snippets[:4]:
            t = re.sub(r"<[^>]+>", "", s)
            t = html.unescape(t).strip()
            if t:
                cleaned.append(t)
        if not cleaned:
            return "I could not find any information on the web, sir."
        joined = "\n".join(cleaned)
        chat_fn = ctx.get("chat")
        if chat_fn:
            reply = chat_fn(
                f"The user asked: '{query}'. "
                f"Synthesize a 1-2 sentence direct answer from these snippets:\n{joined}"
            )
            return reply
        return cleaned[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Web search failed: %s", exc)
        return "The web search failed, sir."


def _handle_reminder(plan: dict, ctx: ExecutorContext) -> str:
    from reminders import (
        add_reminder, list_reminders, remove_reminder, clear_reminders,
    )
    op = (plan.get("op") or "add").lower()
    if op == "list":
        items = list_reminders()
        if not items:
            return "You have no reminders, sir."
        lines = [f"{i+1}. {r['task']} at {r['when']}" for i, r in enumerate(items)]
        return "Here are your reminders, sir: " + "; ".join(lines)
    if op == "clear":
        n = clear_reminders()
        return f"Cleared {n} reminders, sir."
    if op == "remove":
        idx = int(plan.get("index", 0)) - 1  # user is 1-indexed
        if remove_reminder(idx):
            return "Reminder deleted, sir."
        return "I could not find that reminder, sir."
    # default: add
    result = add_reminder(plan.get("time", ""), plan.get("task", ""))
    if not result.get("ok"):
        return f"Reminder failed, sir. {result.get('error', '')}"
    return f"Reminder created, sir. {plan.get('task')} at {result['human_time']}."


def _handle_calendar_event(plan: dict, ctx: ExecutorContext) -> str:
    from calendar_engine import create_calendar_event
    title = plan.get("title") or "event"
    date = plan.get("date") or ""
    time_str = plan.get("time") or ""
    duration = int(plan.get("duration_minutes") or 60)
    result = create_calendar_event(title, date, time_str, duration)
    if not result.get("ok"):
        return f"Calendar event failed, sir. {result.get('error', '')}"
    return (
        f"Meeting scheduled, sir. {title} on {result['human_time']} "
        f"for {result['duration_minutes']} minutes."
    )


def _handle_whatsapp(plan: dict, ctx: ExecutorContext) -> str:
    from whatsapp_actions import send_whatsapp_message
    confirm_fn = ctx.get("confirm_fn")
    result = send_whatsapp_message(
        plan.get("contact", ""),
        plan.get("message", ""),
        confirm_fn=confirm_fn,
        auto_open=True,
    )
    if result.get("cancelled"):
        return result.get("message", "Cancelled, sir.")
    return result.get("tts", "WhatsApp action completed, sir.")


def _handle_email(plan: dict, ctx: ExecutorContext) -> str:
    from email_actions import compose_email
    confirm_fn = ctx.get("confirm_fn")
    result = compose_email(
        plan.get("recipient", ""),
        plan.get("subject", ""),
        plan.get("body", ""),
        confirm_fn=confirm_fn,
        auto_open=True,
    )
    if result.get("cancelled"):
        return result.get("message", "Cancelled, sir.")
    return result.get("tts", "Email drafted, sir.")


def _handle_clipboard(plan: dict, ctx: ExecutorContext) -> str:
    """Read / write / summarize / clear the OS clipboard."""
    import clipboard_tools
    op = (plan.get("op") or "read").lower()
    try:
        if op == "read":
            text = clipboard_tools.read()
            if not text:
                return "Your clipboard is empty, sir."
            preview = text if len(text) <= 400 else text[:400] + "..."
            return f"Your clipboard contains: {preview}"
        if op == "write":
            text = plan.get("text", "") or ""
            if not text:
                return "I did not catch what to copy, sir."
            ok = clipboard_tools.write(text)
            if not ok:
                return "I could not access the clipboard, sir."
            echo = text if len(text) <= 80 else text[:80] + "..."
            return f"Copied '{echo}' to your clipboard, sir."
        if op == "summarize":
            chat_fn = ctx.get("chat")
            return clipboard_tools.summarize(chat_fn=chat_fn)
        if op == "clear":
            ok = clipboard_tools.clear()
            return "Clipboard cleared, sir." if ok else "I could not clear the clipboard, sir."
        return f"Unknown clipboard operation '{op}', sir."
    except Exception as exc:  # noqa: BLE001
        logger.exception("clipboard op failed: %s", op)
        return f"Clipboard operation failed, sir. {exc}"


def _handle_file_operation(plan: dict, ctx: ExecutorContext) -> str:
    import file_manager
    import os
    op = (plan.get("op") or "").strip()
    if not op:
        return "No file operation given, sir."
    allowed = {"name", "path", "query", "dest_folder", "new_name", "content", "folder"}
    params = {k: v for k, v in plan.items() if k in allowed and v is not None}
    if op in ("delete_file",):
        params.setdefault("confirm_fn", ctx.get("confirm_fn"))
    result = file_manager.run(op, **params)
    tts = result.get("tts") or "File operation completed, sir."
    if op in ("create_file",) and result.get("ok", False):
        path = result.get("path", "")
        if path and os.path.isfile(path):
            try:
                subprocess.Popen(["cmd", "/c", "start", "", path],
                                 shell=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                tts = result.get("tts", "") + " Opening file, sir."
            except Exception:
                pass
    return tts


def _handle_folder_operation(plan: dict, ctx: ExecutorContext) -> str:
    import file_manager
    op = (plan.get("op") or "").strip()
    if not op:
        return "No folder operation given, sir."
    allowed = {"name", "path", "parent"}
    params = {k: v for k, v in plan.items() if k in allowed and v is not None}
    if op in ("delete_folder",):
        params.setdefault("confirm_fn", ctx.get("confirm_fn"))
    result = file_manager.run(op, **params)
    return result.get("tts") or "Folder operation completed, sir."


def _handle_pc_control(plan: dict, ctx: ExecutorContext) -> str:
    import pc_control
    phrase = (plan.get("phrase") or plan.get("op") or "").strip()
    if not phrase:
        return "No PC command given, sir."
    confirm_fn = ctx.get("confirm_fn")
    result = pc_control.execute(phrase, confirm_fn=confirm_fn)
    if result.get("cancelled"):
        return result.get("tts") or "Cancelled, sir."
    return result.get("tts") or "PC command completed, sir."


def _handle_screenshot(plan: dict, ctx: ExecutorContext) -> str:
    path = _capture_screen()
    if not path:
        return "Screenshot failed, sir."
    return f"Screenshot captured, sir. Saved to {os.path.basename(path)}."


def _handle_screen_awareness(plan: dict, ctx: ExecutorContext) -> str:
    op = (plan.get("op") or "describe").lower()
    prompts = {
        "describe": "Describe everything visible on this screen in a concise and useful way.",
        "error": (
            "Analyze this screenshot and explain any visible errors, warnings, "
            "exceptions, stack traces, compiler errors, terminal errors, IDE "
            "errors, or browser errors. Suggest fixes."
        ),
        "code_review": (
            "Analyze visible source code and explain what it does. Identify "
            "bugs and improvements."
        ),
        "summarize_document": (
            "Read all visible text and provide a concise summary."
        ),
    }
    prompt = prompts.get(op, prompts["describe"])

    speak = ctx.get("speak")
    if speak:
        if op == "error":
            speak("Analyzing the error on your screen, sir.")
        elif op == "code_review":
            speak("Reviewing the code on your screen, sir.")
        elif op == "summarize_document":
            speak("Reading and summarizing the document, sir.")
        else:
            speak("Analyzing your screen, sir. Please hold.")

    path = _capture_screen()
    if not path:
        return "Failed to capture screenshot, sir."

    try:
        import ollama
        resp = ollama.chat(
            model="qwen2.5vl:3b",
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [path],
            }],
        )
        analysis = resp["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Screen analysis failed: %s", exc)
        return f"I encountered an error during screen analysis, sir. {exc}"

    analysis = _clean_for_speech(analysis)
    if speak:
        speak(analysis)
    return analysis


def _clean_for_speech(text: str) -> str:
    import re
    cleaned = re.sub(r"[*#`_\-~]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _handle_volume_control(plan: dict, ctx: ExecutorContext) -> str:
    op = (plan.get("op") or "").lower()
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER

        speakers = AudioUtilities.GetSpeakers()
        volume = speakers.EndpointVolume
        if op == "up":
            cur = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(min(cur + 0.1, 1.0), None)
            return "Volume increased, sir."
        if op == "down":
            cur = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(max(cur - 0.1, 0.0), None)
            return "Volume decreased, sir."
        if op == "mute":
            volume.SetMute(1, None)
            return "Audio muted, sir."
        if op == "unmute":
            volume.SetMute(0, None)
            return "Audio restored, sir."
        if op == "set":
            level = max(0, min(int(plan.get("level", 50)), 100))
            volume.SetMasterVolumeLevelScalar(level / 100, None)
            return f"Volume set to {level} percent, sir."
    except Exception as exc:  # noqa: BLE001
        logger.warning("Volume control failed: %s", exc)
    return "Volume adjustment failed, sir."


def _handle_system_control(plan: dict, ctx: ExecutorContext) -> str:
    op = (plan.get("op") or "").lower()
    speak = ctx.get("speak")
    if "lock" in op:
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "Locking computer, sir."
    if "shutdown" in op:
        if speak:
            speak("Shutting down computer.")
        os.system("shutdown /s /t 5")
        return "Shutting down, sir."
    if "restart" in op:
        if speak:
            speak("Restarting computer.")
        os.system("shutdown /r /t 5")
        return "Restarting, sir."
    return "Unknown system control, sir."


def _handle_time(plan: dict, ctx: ExecutorContext) -> str:
    return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


def _handle_date(plan: dict, ctx: ExecutorContext) -> str:
    return f"Today is {datetime.now().strftime('%d %B %Y')}, sir."


def _handle_system_stats(plan: dict, ctx: ExecutorContext) -> str:
    import psutil
    metric = (plan.get("metric") or "").lower()
    if "battery" in metric:
        b = psutil.sensors_battery()
        if b:
            return f"Battery is at {b.percent} percent, sir."
        return "Battery information is unavailable, sir."
    if "ram" in metric or "memory" in metric:
        ram = psutil.virtual_memory()
        used = round(ram.used / (1024**3), 1)
        total = round(ram.total / (1024**3), 1)
        return f"RAM usage is {used} gigabytes out of {total} gigabytes, sir."
    if "cpu" in metric or "processor" in metric:
        cpu = psutil.cpu_percent(interval=1)
        return f"CPU usage is {cpu} percent, sir."
    return "Which metric, sir? Battery, CPU, or RAM?"


def _handle_music(plan: dict, ctx: ExecutorContext) -> str:
    import keyboard
    op = (plan.get("op") or "").lower()
    if op in ("play", "pause", "stop", "play pause"):
        keyboard.send("play/pause media")
        return "Media toggled, sir."
    if op in ("next", "skip"):
        keyboard.send("next track")
        return "Skipping track, sir."
    if op == "previous":
        keyboard.send("previous track")
        return "Returning to previous track, sir."
    return "Unknown music command, sir."


def _handle_memory_store(plan: dict, ctx: ExecutorContext) -> str:
    fact = (plan.get("fact") or "").strip()
    if not fact:
        return "I didn't catch the fact to remember, sir."
    memory = ctx.get("memory")
    if not memory:
        return "Memory subsystem is unavailable, sir."
    data = memory.load()
    data.setdefault("facts", []).append(fact)
    memory.save(data)
    return "I will remember that, sir."


def _handle_memory_recall(plan: dict, ctx: ExecutorContext) -> str:
    memory = ctx.get("memory")
    if not memory:
        return "Memory subsystem is unavailable, sir."
    data = memory.load()
    facts = data.get("facts", [])
    if not facts:
        return "I don't have any facts stored in my memory, sir."
    return "Here is what I remember about you, sir: " + "; ".join(facts)


def _handle_memory_clear(plan: dict, ctx: ExecutorContext) -> str:
    memory = ctx.get("memory")
    if not memory:
        return "Memory subsystem is unavailable, sir."
    memory.save({"facts": []})
    return "I have cleared my memory, sir."


def _handle_ai_chat(plan: dict, ctx: ExecutorContext) -> str:
    chat_fn = ctx.get("chat")
    text = plan.get("text") or ""
    if chat_fn and text:
        return chat_fn(text)
    return "I am ready, sir."


# ---------------------------------------------------------------------------
# UPDATED: Production-grade search handlers using prioritized_search_agent
# ---------------------------------------------------------------------------
def _handle_search_in_app(plan: dict, ctx: ExecutorContext) -> str:
    """
    Search within an application using prioritized fallback methods.
    Uses the new search_agent with Accessibility -> OCR -> Keyboard -> Vision.
    """
    from search_agent import search_agent
    from ui_core import WindowManager, automator
    
    query = (plan.get("query") or "").strip()
    app = (plan.get("app") or "").strip()
    
    if not query:
        return "I did not catch what to search for, sir."
    if not app:
        return "I did not catch which app to search in, sir."
    
    speak = ctx.get("speak")
    if speak:
        speak(f"Searching for {query} in {app}, sir.")
    
    try:
        # Get active window first (if app not specified in window title)
        wm = WindowManager()
        active = wm.get_active_window()
        
        if active:
            # Try to search in active window first
            result = search_agent.search(query, app, active.hwnd)
            if result.success:
                return result.message
        
        # If active window search failed or no active window, try to find app window
        from app_launcher import app_launcher
        
        # Check if app is running
        window_info = wm.find_window_for_app(app)
        
        if not window_info:
            # App not running, launch it
            launch_result = app_launcher.launch_and_verify(app, wait_for_ui=True)
            if launch_result.status.value != "success":
                return f"Could not open {app} to search, sir. {launch_result.message}"
            window_info = {'hwnd': launch_result.hwnd}
        
        # Execute search
        result = search_agent.search(query, app, window_info['hwnd'])
        
        if result.success:
            return result.message
        else:
            # Fallback to old search method
            return automator.search_in_app(query, app)
            
    except Exception as exc:
        logger.exception(f"search_in_app failed for {app}")
        return f"Failed to search in {app}, sir. {exc}"


def _handle_search_in_app_v2(plan: dict, ctx: ExecutorContext) -> str:
    """
    Universal search using the new prioritized search agent.
    This is the recommended handler for all search operations.
    """
    from search_agent import search_agent
    from ui_core import WindowManager
    
    query = (plan.get("query") or "").strip()
    app = (plan.get("app") or "").strip()
    
    if not query:
        return "I did not catch what to search for, sir."
    if not app:
        return "I did not catch which app to search in, sir."
    
    speak = ctx.get("speak")
    if speak:
        speak(f"Searching for {query} in {app}, sir.")
    
    try:
        wm = WindowManager()
        
        # Try to find the app window
        window_info = wm.find_window_for_app(app)
        
        if not window_info:
            # App not running, launch it using app_launcher
            from app_launcher import app_launcher
            launch_result = app_launcher.launch_and_verify(app, wait_for_ui=True)
            
            if launch_result.status.value != "success":
                return f"Could not open {app} to search, sir. {launch_result.message}"
            
            window_info = {'hwnd': launch_result.hwnd}
            # Wait a moment for UI to stabilize
            time.sleep(1.0)
        
        # Ensure window is focused
        if not wm.focus_window(window_info['hwnd']):
            return f"Could not focus {app} to search, sir."
        
        time.sleep(0.5)  # Wait for focus to settle
        
        # Execute prioritized search
        result = search_agent.search(query, app, window_info['hwnd'])
        
        if result.success:
            logger.info(f"Search successful using method: {result.method.value if result.method else 'unknown'}")
            return result.message
        else:
            return f"Could not find a search field in {app}, sir. Please try manually."
            
    except Exception as exc:
        logger.exception(f"search_in_app_v2 failed for {app}")
        return f"Failed to search in {app}, sir. {exc}"


def _handle_close_app(plan: dict, ctx: ExecutorContext) -> str:
    app = (plan.get("app") or "").strip()
    if not app:
        return "I did not catch the application to close, sir."
    try:
        subprocess.run(["taskkill", "/IM", app + ".exe", "/F"],
                       capture_output=True, text=True, timeout=5)
        return f"Closed {app}, sir."
    except subprocess.TimeoutExpired:
        return f"Timed out trying to close {app}, sir."
    except Exception as exc:
        logger.warning("close_app failed: %s", exc)
        return f"Failed to close {app}, sir. {exc}"


def _handle_switch_window(plan: dict, ctx: ExecutorContext) -> str:
    target = (plan.get("target") or "").strip()
    if not target:
        return "I did not catch the window to switch to, sir."
    try:
        import subprocess
        script = (
            f'$wshell = New-Object -ComObject WScript.Shell; '
            f'$wshell.AppActivate("{target}")'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, text=True, timeout=5)
        return f"Switched to {target}, sir."
    except Exception as exc:
        logger.warning("switch_window failed: %s", exc)
        return f"Failed to switch to {target}, sir. {exc}"


def _handle_open_folder(plan: dict, ctx: ExecutorContext) -> str:
    path = (plan.get("path") or "").strip()
    if not path:
        return "I did not catch the folder to open, sir."
    import pc_control
    result = pc_control.execute(f"open {path}")
    return result.get("tts") or f"Opening {path}, sir."


def _handle_focus_window(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    title = (plan.get("title") or plan.get("target") or "").strip()
    if not title:
        return "I did not catch the window to focus, sir."
    return automator.focus_window(title)


def _handle_hotkey(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    keys = plan.get("keys") or []
    if isinstance(keys, str):
        keys = keys.split("+")
    if not keys:
        return "No hotkey specified, sir."
    return automator.hotkey(*keys)


def _handle_move_mouse(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    x = plan.get("x")
    y = plan.get("y")
    if x is None or y is None:
        return "I need both x and y coordinates, sir."
    return automator.move_mouse(int(x), int(y))


def _handle_wait_for_window(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    title = (plan.get("title") or plan.get("target") or "").strip()
    if not title:
        return "I did not catch the window to wait for, sir."
    timeout = float(plan.get("timeout", 15))
    return automator.wait_for_window(title, timeout=timeout)


def _handle_wait_for_element(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    automation_id = (plan.get("automation_id") or "").strip() or None
    text = (plan.get("text") or "").strip() or None
    if not automation_id and not text:
        return "I need an automation_id or text to locate, sir."
    timeout = float(plan.get("timeout", 10))
    return automator.wait_for_element(
        automation_id=automation_id, text=text, timeout=timeout
    )


def _handle_click(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    return automator.click(
        x=plan.get("x"), y=plan.get("y"), button=plan.get("button", "left")
    )


def _handle_double_click(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    return automator.double_click(x=plan.get("x"), y=plan.get("y"))


def _handle_right_click(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    return automator.right_click(x=plan.get("x"), y=plan.get("y"))


def _handle_type_text(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    text = (plan.get("text") or "").strip()
    return automator.type_text(text)


def _handle_press_key(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    key = (plan.get("key") or "").strip()
    return automator.press_key(key)


def _handle_scroll(plan: dict, ctx: ExecutorContext) -> str:
    from ui_core import automator
    direction = (plan.get("direction") or "down").lower()
    amount = int(plan.get("amount") or 3)
    return automator.scroll(direction=direction, amount=amount)


def _handle_browser_open(plan: dict, ctx: ExecutorContext) -> str:
    url = (plan.get("url") or "").strip()
    if not url:
        return "I did not catch the URL, sir."
    try:
        webbrowser.open(url if url.startswith("http") else "https://" + url)
        return f"Opening {url}, sir."
    except Exception as exc:
        return f"Failed to open browser, sir. {exc}"


def _handle_browser_search(plan: dict, ctx: ExecutorContext) -> str:
    query = (plan.get("query") or "").strip()
    if not query:
        return "I did not catch the search query, sir."
    try:
        import urllib.parse
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return f"Searching for {query} in browser, sir."
    except Exception as exc:
        return f"Failed to search browser, sir. {exc}"


def _handle_browser_click(plan: dict, ctx: ExecutorContext) -> str:
    element = (plan.get("element") or "").strip()
    if not element:
        return "I did not catch the element to click, sir."
    return f"Please click on {element} in the browser, sir."


def _handle_run_program(plan: dict, ctx: ExecutorContext) -> str:
    program = (plan.get("program") or "").strip()
    if not program:
        return "I did not catch the program to run, sir."
    try:
        subprocess.Popen(program, shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Running {program}, sir."
    except Exception as exc:
        return f"Failed to run {program}, sir. {exc}"


def _handle_run_terminal_command(plan: dict, ctx: ExecutorContext) -> str:
    command = (plan.get("command") or "").strip()
    if not command:
        return "I did not catch the command to execute, sir."
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=30,
        )
        output = (result.stdout or "").strip()[:400]
        if output:
            return f"Command executed, sir. Output: {output}"
        return f"Command executed, sir."
    except subprocess.TimeoutExpired:
        return f"Command timed out, sir."
    except Exception as exc:
        logger.warning("run_command failed: %s", exc)
        return f"Command failed, sir. {exc}"


def _handle_generate_code(plan: dict, ctx: ExecutorContext) -> str:
    import code_generator
    description = (plan.get("description") or "").strip()
    language = (plan.get("language") or "").strip()
    target_file = (plan.get("target_file") or "").strip()
    result = code_generator.generate_code(description, language)
    if not result.get("ok"):
        return result.get("tts", "Code generation failed, sir.")
    code = result.get("code", "")
    if not code:
        return "Code generation produced no output, sir."
    if target_file:
        write_result = code_generator.write_code_to_file(code, target_file)
        if write_result.get("ok"):
            path = write_result.get("path", target_file)
            parts = []
            parts.append(write_result.get("tts", f"Code written to {os.path.basename(path)}, sir."))
            try:
                if os.path.isfile(path):
                    subprocess.Popen(["cmd", "/c", "start", "", path],
                                     shell=True,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    parts.append("Opening file, sir.")
            except Exception:
                pass
            return " ".join(parts)
        return write_result.get("tts", "Failed to write generated code, sir.")
    chat_fn = ctx.get("chat")
    if chat_fn and code:
        chat_fn(f"Here is the generated code:\n{code}")
    return "Code generated, sir."


def _handle_set_reminder(plan: dict, ctx: ExecutorContext) -> str:
    return _handle_reminder(plan, ctx)


def _handle_wait(plan: dict, ctx: ExecutorContext) -> str:
    seconds = int(plan.get("seconds") or 3)
    time.sleep(seconds)
    return f"Waited for {seconds} seconds, sir."


def _handle_diagnostics(plan: dict, ctx: ExecutorContext) -> str:
    """Run JARVIS diagnostics and return results."""
    try:
        from diagnostics import check_environment, get_report_text
        report = check_environment()
        text = get_report_text(report)
        for line in text.split("\n"):
            logger.info("DIAG: %s", line)
        chat_fn = ctx.get("chat")
        if chat_fn:
            chat_fn(f"Diagnostics report:\n{text}")
        issues = []
        libs = report.get("libraries", {})
        if libs.get("pywinauto") == "NOT INSTALLED":
            issues.append("pywinauto not installed (run: pip install pywinauto)")
        if libs.get("pyautogui") == "NOT INSTALLED":
            issues.append("pyautogui not installed")
        if libs.get("pytesseract") == "NOT INSTALLED":
            issues.append("pytesseract not installed (OCR fallback unavailable)")
        if not report.get("accessibility"):
            issues.append("Accessibility APIs unavailable")
        if not report.get("win32_api"):
            issues.append("Win32 API unavailable (window detection broken)")
        if not report.get("window_manager"):
            issues.append("Window manager not working")
        if issues:
            return f"Diagnostics completed, sir. Issues found: {'; '.join(issues)}"
        return "Diagnostics completed, sir. All systems operational."
    except Exception as exc:
        logger.exception("Diagnostics failed")
        return f"Diagnostics failed, sir. {exc}"


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------
HANDLERS: Dict[str, Callable[[dict, ExecutorContext], str]] = {
    "open_app": _handle_open_app,
    "close_app": _handle_close_app,
    "switch_window": _handle_switch_window,
    "web_search": _handle_web_search,
    "search_in_app": _handle_search_in_app,
    "search_in_app_v2": _handle_search_in_app_v2,  # Recommended
    "reminder": _handle_reminder,
    "set_reminder": _handle_set_reminder,
    "calendar_event": _handle_calendar_event,
    "whatsapp": _handle_whatsapp,
    "email": _handle_email,
    "clipboard": _handle_clipboard,
    "file_operation": _handle_file_operation,
    "folder_operation": _handle_folder_operation,
    "pc_control": _handle_pc_control,
    "screenshot": _handle_screenshot,
    "screen_awareness": _handle_screen_awareness,
    "system_control": _handle_system_control,
    "volume_control": _handle_volume_control,
    "memory_store": _handle_memory_store,
    "memory_recall": _handle_memory_recall,
    "memory_clear": _handle_memory_clear,
    "time": _handle_time,
    "date": _handle_date,
    "system_stats": _handle_system_stats,
    "music": _handle_music,
    "focus_window": _handle_focus_window,
    "hotkey": _handle_hotkey,
    "move_mouse": _handle_move_mouse,
    "wait_for_window": _handle_wait_for_window,
    "wait_for_element": _handle_wait_for_element,
    "click": _handle_click,
    "double_click": _handle_double_click,
    "right_click": _handle_right_click,
    "type_text": _handle_type_text,
    "press_key": _handle_press_key,
    "scroll": _handle_scroll,
    "browser_open": _handle_browser_open,
    "browser_search": _handle_browser_search,
    "browser_click": _handle_browser_click,
    "run_program": _handle_run_program,
    "run_terminal_command": _handle_run_terminal_command,
    "generate_code": _handle_generate_code,
    "wait": _handle_wait,
    "diagnostics": _handle_diagnostics,
    "ai_chat": _handle_ai_chat,
}


def register_default_handlers() -> None:
    """Wire all HANDLERS into planner.register_tool."""
    for action, fn in HANDLERS.items():
        register_tool(action, _wrap(fn))


_CTX: Optional[ExecutorContext] = None


def set_executor_context(ctx: ExecutorContext) -> None:
    global _CTX
    _CTX = ctx


def _wrap(fn: Callable[[dict, ExecutorContext], str]) -> Callable[[dict], str]:
    def _inner(plan: dict) -> str:
        return fn(plan, _CTX or {})
    return _inner


# ---------------------------------------------------------------------------
# Execution context
# ---------------------------------------------------------------------------
_EXEC_METRICS: dict = {
    "total_calls": 0,
    "last_duration_ms": 0,
    "average_duration_ms": 0,
    "failures": 0,
    "successes": 0,
}

_EXEC_CTX: dict = {
    "last_folder": "",
    "last_file": "",
    "last_clipboard": "",
    "last_search_result": "",
    "last_screenshot": "",
    "current_window": "",
    "current_app": "",
    "current_file": "",
    "current_folder": "",
}


def set_executor_context_value(key: str, value: str) -> None:
    if key in _EXEC_CTX:
        _EXEC_CTX[key] = value


def get_execution_metrics() -> dict:
    m = dict(_EXEC_METRICS)
    if m["total_calls"] > 0:
        m["average_duration_ms"] = m["last_duration_ms"]
    return m


def _update_exec_context(plan: dict, tts_result: str) -> None:
    action = plan.get("action", "")
    op = plan.get("op", "")
    folder = plan.get("folder", "")
    if action == "folder_operation":
        if op == "create_folder":
            name = plan.get("name", "")
            _EXEC_CTX["last_folder"] = name
            _EXEC_CTX["current_folder"] = name
        elif op == "rename_folder":
            new_name = plan.get("new_name", "")
            _EXEC_CTX["last_folder"] = new_name
            _EXEC_CTX["current_folder"] = new_name
    if action == "file_operation":
        pname = plan.get("name", "")
        ppath = plan.get("path", "")
        if op == "create_file":
            _EXEC_CTX["last_file"] = pname
            _EXEC_CTX["current_file"] = pname
            if folder:
                _EXEC_CTX["current_folder"] = os.path.basename(folder.rstrip("/\\"))
        elif op in ("open_file", "write_file", "append_file", "read_file"):
            _EXEC_CTX["last_file"] = ppath
            _EXEC_CTX["current_file"] = ppath
    if action == "clipboard":
        if op == "write":
            _EXEC_CTX["last_clipboard"] = plan.get("text", "")
        elif op == "read":
            _EXEC_CTX["last_clipboard"] = tts_result
    if action == "screenshot":
        _EXEC_CTX["last_screenshot"] = tts_result
    if action == "web_search":
        _EXEC_CTX["last_search_result"] = tts_result
    if action == "open_app":
        _EXEC_CTX["last_app"] = plan.get("app", "")
        _EXEC_CTX["current_app"] = plan.get("app", "")
    if action == "browser_open":
        _EXEC_CTX["last_url"] = plan.get("url", "")
    if action in ("focus_window", "wait_for_window"):
        title = plan.get("title", "") or plan.get("target", "")
        if title:
            _EXEC_CTX["current_window"] = title
    if action in ("search_in_app", "search_in_app_v2"):
        _EXEC_CTX["current_app"] = plan.get("app", "")
        _EXEC_CTX["current_window"] = plan.get("app", "")


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------
def _polish_tts(text: str) -> str:
    import re
    if not text:
        return text
    text = re.sub(r"\bsir\b[,\s]*\bsir\b", "sir", text, flags=re.IGNORECASE)
    text = re.sub(r"([.!?]){2,}", r"\1", text)
    text = re.sub(r",\s*\.", ".", text)
    text = re.sub(r"\.(\w)", ". \\1", text)
    return text.strip()


def execute_plan(plan: dict) -> str:
    from planner import _dispatch as _planner_dispatch

    t0 = time.perf_counter()
    _EXEC_METRICS["total_calls"] += 1

    if not isinstance(plan, dict):
        _EXEC_METRICS["failures"] += 1
        _EXEC_METRICS["last_duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return "I received an invalid plan, sir."

    try:
        if "steps" in plan:
            results: list[str] = []
            for idx, step in enumerate(plan["steps"]):
                action = step.get("action", "unknown")
                logger.info("Executing step %d/%d: %s",
                            idx + 1, len(plan["steps"]), action)
                try:
                    result = _planner_dispatch(step)
                    if result:
                        results.append(result)
                    _update_exec_context(step, result or "")
                except Exception as exc:
                    logger.warning("Step %d (%s) failed: %s", idx + 1, action, exc)
                    results.append(f"Step {idx + 1} failed, sir.")
                    continue
            if not results:
                _EXEC_METRICS["successes"] += 1
                _EXEC_METRICS["last_duration_ms"] = int((time.perf_counter() - t0) * 1000)
                return _polish_tts("Task completed, sir.")
            if len(results) == 1:
                _EXEC_METRICS["successes"] += 1
                _EXEC_METRICS["last_duration_ms"] = int((time.perf_counter() - t0) * 1000)
                return _polish_tts(results[0])
            _EXEC_METRICS["successes"] += 1
            _EXEC_METRICS["last_duration_ms"] = int((time.perf_counter() - t0) * 1000)
            return _polish_tts(" ".join(results))

        result = _planner_dispatch(plan)
        _update_exec_context(plan, result or "")
        _EXEC_METRICS["successes"] += 1
        _EXEC_METRICS["last_duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return _polish_tts(result if result else "Task completed, sir.")
    except Exception as exc:
        logger.error("execute_plan failed: %s", exc)
        _EXEC_METRICS["failures"] += 1
        _EXEC_METRICS["last_duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return _polish_tts("Execution failed, sir.")