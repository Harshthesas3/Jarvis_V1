"""Action handler classes for the execution engine.

Each handler maps to a specific action name and contains the
execution logic previously found in adapter.py handler functions.
"""

from __future__ import annotations

from jarvis.interfaces.executor import TaskHandler
from jarvis.types import TaskNode


class OpenAppHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "open_app"

    def execute(self, task: TaskNode, context: dict) -> str:
        from app_launcher import app_launcher
        import logging, os, re, subprocess
        logger = logging.getLogger("jarvis.execution.handlers")
        apps = context.get("apps", [])
        raw = (task.params.get("app") or "").strip().lower().replace(".", "")
        if not raw:
            return "No app specified."
        ALIAS_MAP = {"vs code": "Visual Studio Code", "vscode": "Visual Studio Code",
                     "code": "Visual Studio Code", "chrome": "Google Chrome",
                     "edge": "Microsoft Edge", "spotify": "Spotify",
                     "terminal": "Terminal", "cmd": "Command Prompt",
                     "notepad": "Notepad", "calculator": "Calculator"}
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
                os.startfile(re.sub(r'[^a-zA-Z0-9_\-.\\:]', '', fn))
                return f"Opening {fn}."
        except Exception:
            pass
        return "App not found."


class CloseAppHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "close_app"

    def execute(self, task: TaskNode, context: dict) -> str:
        import re, subprocess
        app = re.sub(r'[^a-zA-Z0-9_.-]', '', (task.params.get("app") or "").strip())
        if not app:
            return "No app."
        try:
            subprocess.run(["taskkill", "/IM", app + ".exe", "/F"], capture_output=True, text=True, timeout=5)
            return f"Closed {app}."
        except Exception as e:
            return f"Failed: {e}"


class WebSearchHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "web_search"

    def execute(self, task: TaskNode, context: dict) -> str:
        import html, re, urllib.parse, urllib.request
        q = (task.params.get("query") or "").strip()
        if not q:
            return "No query."
        try:
            d = urllib.parse.urlencode({"q": q}).encode()
            req = urllib.request.Request(
                "https://lite.duckduckgo.com/lite/",
                data=d,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                p = r.read().decode("utf-8")
            snippets = [
                html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
                for s in re.findall(
                    r"class=[\x22\x27]result-snippet[\x22\x27][^>]*>(.*?)</",
                    p,
                    re.DOTALL,
                )
            ][:4]
            if not snippets:
                return "No results."
            chat = context.get("chat")
            if chat:
                return chat(f"User asked: {q}. Answer from: {' '.join(snippets)}")
            return snippets[0]
        except Exception as e:
            return f"Search failed: {e}"


class TimeHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "time"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class DateHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "date"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"Today is {datetime.now().strftime('%d %B %Y')}, sir."


class ReminderHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "reminder"

    def execute(self, task: TaskNode, context: dict) -> str:
        from reminders import add_reminder, clear_reminders, list_reminders, remove_reminder
        op = (task.params.get("op") or "add").lower()
        if op == "list":
            items = list_reminders()
            return "No reminders." if not items else "Reminders: " + "; ".join(
                f"{i+1}. {r['task']}" for i, r in enumerate(items)
            )
        if op == "clear":
            return f"Cleared {clear_reminders()} reminders."
        if op == "remove":
            return "Reminder deleted." if remove_reminder(int(task.params.get("index", 0)) - 1) else "Not found."
        r = add_reminder(task.params.get("time", ""), task.params.get("task", ""))
        return f"Reminder set for {r.get('human_time', '?')}."


class ClipboardHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "clipboard"

    def execute(self, task: TaskNode, context: dict) -> str:
        import clipboard_tools
        op = (task.params.get("op") or "read").lower()
        if op == "read":
            t = clipboard_tools.read()
            return f"Clipboard: {t[:400]}" if t else "Clipboard empty."
        if op == "write":
            clipboard_tools.write(task.params.get("text", ""))
            return "Copied."
        if op == "clear":
            clipboard_tools.clear()
            return "Cleared."
        return "Done."


class ScreenshotHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "screenshot"

    def execute(self, task: TaskNode, context: dict) -> str:
        import mss, os
        from datetime import datetime
        try:
            os.makedirs("Screenshots", exist_ok=True)
            p = f"Screenshots/shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            with mss.MSS() as s:
                s.shot(output=p)
            return "Screenshot saved."
        except Exception as e:
            return f"Screenshot failed: {e}"


class VolumeControlHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "volume_control"

    def execute(self, task: TaskNode, context: dict) -> str:
        op = (task.params.get("op") or "").lower()
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            from ctypes import cast, POINTER
            v = AudioUtilities.GetSpeakers().EndpointVolume
            if op == "up":
                v.SetMasterVolumeLevelScalar(min(v.GetMasterVolumeLevelScalar() + 0.1, 1.0), None)
                return "Volume up."
            if op == "down":
                v.SetMasterVolumeLevelScalar(max(v.GetMasterVolumeLevelScalar() - 0.1, 0.0), None)
                return "Volume down."
            if op == "mute":
                v.SetMute(1, None)
                return "Muted."
            if op == "unmute":
                v.SetMute(0, None)
                return "Unmuted."
            if op == "set":
                v.SetMasterVolumeLevelScalar(
                    max(0, min(int(task.params.get("level", 50)), 100)) / 100, None
                )
                return f"Volume set to {task.params.get('level')}%."
        except Exception:
            pass
        return "Volume command failed."


class SystemControlHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "system_control"

    def execute(self, task: TaskNode, context: dict) -> str:
        import subprocess
        op = (task.params.get("op") or "").lower()
        if "lock" in op:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], capture_output=True, timeout=5)
            return "Locking."
        if "shutdown" in op:
            subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True, timeout=5)
            return "Shutting down."
        if "restart" in op:
            subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True, timeout=5)
            return "Restarting."
        return "Unknown."


class FileOperationHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "file_operation"

    def execute(self, task: TaskNode, context: dict) -> str:
        import file_manager
        op = (task.params.get("op") or "").strip()
        if not op:
            return "No operation."
        allowed = {"name", "path", "query", "dest_folder", "new_name", "content", "folder"}
        params = {k: v for k, v in task.params.items() if k in allowed and v is not None}
        return file_manager.run(op, **params).get("tts") or "File operation done."


class FolderOperationHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "folder_operation"

    def execute(self, task: TaskNode, context: dict) -> str:
        import file_manager
        op = (task.params.get("op") or "").strip()
        if not op:
            return "No operation."
        allowed = {"name", "path", "parent"}
        params = {k: v for k, v in task.params.items() if k in allowed and v is not None}
        return file_manager.run(op, **params).get("tts") or "Folder operation done."


class AIChatHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "ai_chat"

    def execute(self, task: TaskNode, context: dict) -> str:
        chat = context.get("chat")
        t = task.params.get("text", "")
        return chat(t) if chat and t else "Ready."


class BrowserOpenHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "browser_open"

    def execute(self, task: TaskNode, context: dict) -> str:
        import webbrowser
        url = (task.params.get("url") or "").strip()
        if not url:
            return "No URL."
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return f"Opening {url}."
        except Exception as e:
            return f"Failed: {e}"


class BrowserSearchHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "browser_search"

    def execute(self, task: TaskNode, context: dict) -> str:
        import urllib.parse, webbrowser
        q = (task.params.get("query") or "").strip()
        if q:
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(q)}")
            return f"Searching {q}."
        return "No query."


class MusicHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "music"

    def execute(self, task: TaskNode, context: dict) -> str:
        import keyboard
        op = (task.params.get("op") or "").lower()
        if op in ("play", "pause"):
            keyboard.send("play/pause media")
            return "Toggled."
        if op in ("next", "skip"):
            keyboard.send("next track")
            return "Skipped."
        if op == "previous":
            keyboard.send("previous track")
            return "Previous."
        return "Unknown music command."


class MemoryStoreHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "memory_store"

    def execute(self, task: TaskNode, context: dict) -> str:
        fact = (task.params.get("fact") or "").strip()
        mem = context.get("memory")
        if not fact or not mem:
            return "Memory unavailable."
        d = mem.load()
        d.setdefault("facts", []).append(fact)
        mem.save(d)
        return "Remembered."


class MemoryRecallHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "memory_recall"

    def execute(self, task: TaskNode, context: dict) -> str:
        mem = context.get("memory")
        if not mem:
            return "Memory unavailable."
        facts = mem.load().get("facts", [])
        return "No facts." if not facts else "Remember: " + "; ".join(facts)


class MemoryClearHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "memory_clear"

    def execute(self, task: TaskNode, context: dict) -> str:
        mem = context.get("memory")
        if not mem:
            return "Memory unavailable."
        mem.save({"facts": []})
        return "Cleared."


class ClickHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "click"

    def execute(self, task: TaskNode, context: dict) -> str:
        from ui_core import automator
        return automator.click(
            x=task.params.get("x"),
            y=task.params.get("y"),
            button=task.params.get("button", "left"),
        )


class DoubleClickHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "double_click"

    def execute(self, task: TaskNode, context: dict) -> str:
        from ui_core import automator
        return automator.double_click(x=task.params.get("x"), y=task.params.get("y"))


class RightClickHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "right_click"

    def execute(self, task: TaskNode, context: dict) -> str:
        from ui_core import automator
        return automator.right_click(x=task.params.get("x"), y=task.params.get("y"))


class TypeTextHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "type_text"

    def execute(self, task: TaskNode, context: dict) -> str:
        from ui_core import automator
        return automator.type_text((task.params.get("text") or "").strip())


class PressKeyHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "press_key"

    def execute(self, task: TaskNode, context: dict) -> str:
        from ui_core import automator
        return automator.press_key((task.params.get("key") or "").strip())


class ScrollHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "scroll"

    def execute(self, task: TaskNode, context: dict) -> str:
        from ui_core import automator
        return automator.scroll(
            direction=task.params.get("direction", "down"),
            amount=int(task.params.get("amount", 3)),
        )


class RunTerminalCommandHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "run_terminal_command"

    def execute(self, task: TaskNode, context: dict) -> str:
        import re, subprocess
        cmd = (task.params.get("command") or "").strip()
        if not cmd or len(cmd) > 512 or not re.match(r"^[\w\s\-.:\\/@]+$", cmd):
            return "Invalid command."
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=15,
            )
            o = (r.stdout or "").strip()[:400]
            return f"Done. {o}" if o else "Done."
        except subprocess.TimeoutExpired:
            return "Timed out."
        except Exception as e:
            return f"Failed: {e}"


class ScreenAwarenessHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "screen_awareness"

    def execute(self, task: TaskNode, context: dict) -> str:
        import mss, ollama, os
        from datetime import datetime
        op = task.params.get("op", "describe")
        prompts = {
            "describe": "Describe this screen.",
            "error": "Analyze errors.",
            "code_review": "Review code.",
            "summarize_document": "Summarize.",
        }
        try:
            os.makedirs("Screenshots", exist_ok=True)
            p = f"Screenshots/s_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            with mss.MSS() as s:
                s.shot(output=p)
            from src.jarvis.planner.llm import _get_client
            r = _get_client().chat(
                model="qwen2.5vl:3b",
                messages=[{"role": "user", "content": prompts.get(op, prompts["describe"]), "images": [p]}],
            )
            return r["message"]["content"]
        except Exception as e:
            return f"Screen analysis failed: {e}"


class PCControlHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "pc_control"

    def execute(self, task: TaskNode, context: dict) -> str:
        import subprocess
        op = (task.params.get("op") or "").lower()
        if "lock" in op:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], capture_output=True, timeout=5)
            return "Locking."
        if "shutdown" in op:
            subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True, timeout=5)
            return "Shutting down."
        if "restart" in op:
            subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True, timeout=5)
            return "Restarting."
        return "Unknown."


class SystemStatsHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "system_stats"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class SwitchWindowHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "switch_window"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class FocusWindowHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "focus_window"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class SearchInAppV2Handler(TaskHandler):
    @property
    def action(self) -> str:
        return "search_in_app_v2"

    def execute(self, task: TaskNode, context: dict) -> str:
        import html, re, urllib.parse, urllib.request
        q = (task.params.get("query") or "").strip()
        if not q:
            return "No query."
        try:
            d = urllib.parse.urlencode({"q": q}).encode()
            req = urllib.request.Request(
                "https://lite.duckduckgo.com/lite/",
                data=d,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                p = r.read().decode("utf-8")
            snippets = [
                html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
                for s in re.findall(
                    r"class=[\x22\x27]result-snippet[\x22\x27][^>]*>(.*?)</",
                    p,
                    re.DOTALL,
                )
            ][:4]
            if not snippets:
                return "No results."
            chat = context.get("chat")
            if chat:
                return chat(f"User asked: {q}. Answer from: {' '.join(snippets)}")
            return snippets[0]
        except Exception as e:
            return f"Search failed: {e}"


class EmailHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "email"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class WhatsAppHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "whatsapp"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class CalendarEventHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "calendar_event"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class SetReminderHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "set_reminder"

    def execute(self, task: TaskNode, context: dict) -> str:
        from reminders import add_reminder, clear_reminders, list_reminders, remove_reminder
        op = (task.params.get("op") or "add").lower()
        if op == "list":
            items = list_reminders()
            return "No reminders." if not items else "Reminders: " + "; ".join(
                f"{i+1}. {r['task']}" for i, r in enumerate(items)
            )
        if op == "clear":
            return f"Cleared {clear_reminders()} reminders."
        if op == "remove":
            return "Reminder deleted." if remove_reminder(int(task.params.get("index", 0)) - 1) else "Not found."
        r = add_reminder(task.params.get("time", ""), task.params.get("task", ""))
        return f"Reminder set for {r.get('human_time', '?')}."


class MoveMouseHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "move_mouse"

    def execute(self, task: TaskNode, context: dict) -> str:
        from ui_core import automator
        return automator.type_text((task.params.get("text") or "").strip())


class HotkeyHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "hotkey"

    def execute(self, task: TaskNode, context: dict) -> str:
        from ui_core import automator
        return automator.type_text((task.params.get("text") or "").strip())


class WaitHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "wait"

    def execute(self, task: TaskNode, context: dict) -> str:
        import time
        time.sleep(1)
        return "Waited."


class WaitForWindowHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "wait_for_window"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class WaitForElementHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "wait_for_element"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."


class BrowserClickHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "browser_click"

    def execute(self, task: TaskNode, context: dict) -> str:
        import html, re, urllib.parse, urllib.request
        q = (task.params.get("query") or "").strip()
        if not q:
            return "No query."
        try:
            d = urllib.parse.urlencode({"q": q}).encode()
            req = urllib.request.Request(
                "https://lite.duckduckgo.com/lite/",
                data=d,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                p = r.read().decode("utf-8")
            snippets = [
                html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
                for s in re.findall(
                    r"class=[\x22\x27]result-snippet[\x22\x27][^>]*>(.*?)</",
                    p,
                    re.DOTALL,
                )
            ][:4]
            if not snippets:
                return "No results."
            chat = context.get("chat")
            if chat:
                return chat(f"User asked: {q}. Answer from: {' '.join(snippets)}")
            return snippets[0]
        except Exception as e:
            return f"Search failed: {e}"


class RunProgramHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "run_program"

    def execute(self, task: TaskNode, context: dict) -> str:
        from app_launcher import app_launcher
        import logging, os, re, subprocess
        logger = logging.getLogger("jarvis.execution.handlers")
        apps = context.get("apps", [])
        raw = (task.params.get("app") or "").strip().lower().replace(".", "")
        if not raw:
            return "No app specified."
        ALIAS_MAP = {"vs code": "Visual Studio Code", "vscode": "Visual Studio Code",
                     "code": "Visual Studio Code", "chrome": "Google Chrome",
                     "edge": "Microsoft Edge", "spotify": "Spotify",
                     "terminal": "Terminal", "cmd": "Command Prompt",
                     "notepad": "Notepad", "calculator": "Calculator"}
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
                os.startfile(re.sub(r'[^a-zA-Z0-9_\-.\\:]', '', fn))
                return f"Opening {fn}."
        except Exception:
            pass
        return "App not found."


class GenerateCodeHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "generate_code"

    def execute(self, task: TaskNode, context: dict) -> str:
        chat = context.get("chat")
        t = task.params.get("text", "")
        return chat(t) if chat and t else "Ready."


class DiagnosticsHandler(TaskHandler):
    @property
    def action(self) -> str:
        return "diagnostics"

    def execute(self, task: TaskNode, context: dict) -> str:
        from datetime import datetime
        return f"The time is {datetime.now().strftime('%I:%M %p')}, sir."
