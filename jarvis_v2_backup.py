import os
import ollama
import subprocess
import webbrowser
import sounddevice as sd
from scipy.io.wavfile import write
from faster_whisper import WhisperModel
import psutil
import keyboard
import mss
import json
import re
import html
import urllib.request
import urllib.parse
import tkinter as tk
from datetime import datetime
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
import concurrent.futures

PIPER = r"C:\Users\Harshith\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\Scripts\piper.exe"
VOICE = r"C:\Users\Harshith\Downloads\en_US-lessac-medium.onnx"
MEMORY_FILE = "memory.json"

print("Loading models...")

wake_model = WhisperModel(
    "tiny",
    device="cpu",
    compute_type="int8"
)

command_model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

print("Models loaded.")

WAKE_PHRASES = [
    "i'm back",
    "i am back",
    "im back"
]

# --- LOAD INSTALLED APPS ---
try:
    print("Current folder:", os.getcwd())
    print("Apps file exists:", os.path.exists("apps.json"))
    
    # Try reading as UTF-16 first. If that fails, try UTF-8 with BOM, then standard UTF-8
    try:
        with open("apps.json", "r", encoding="utf-16") as f:
            INSTALLED_APPS = json.load(f)
    except Exception:
        try:
            with open("apps.json", "r", encoding="utf-8-sig") as f:
                INSTALLED_APPS = json.load(f)
        except Exception:
            with open("apps.json", "r", encoding="utf-8") as f:
                INSTALLED_APPS = json.load(f)

except Exception as e:
    print("Apps loading error:", e)
    INSTALLED_APPS = []

print(type(INSTALLED_APPS))
if INSTALLED_APPS:
    print(type(INSTALLED_APPS[0]))
    print(INSTALLED_APPS[0])

# --- SYSTEM PROMPT & CHAT HISTORY ---
SYSTEM_PROMPT = """
You are JARVIS.

You are Harshith's personal AI assistant.
Always address Harshith as sir.

Keep answers concise.
Never use emojis.
Never use markdown.
Speak naturally and professionally.
"""

chat_history = []  # Session conversation memory
latest_analysis = {"text": "", "screenshot": ""}  # Latest screen analysis state

# --- MEMORY UTILITIES ---
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"facts": []}
    return {"facts": []}

def save_memory(memory_data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=4)
    except Exception as e:
        print("Error saving memory:", e)

def get_system_prompt():
    memory_data = load_memory()
    facts = memory_data.get("facts", [])
    if facts:
        facts_str = "\n".join(f"- {fact}" for fact in facts)
        return SYSTEM_PROMPT + f"\nHere are facts you remember about Harshith:\n{facts_str}"
    return SYSTEM_PROMPT

# --- CLIPBOARD UTILITIES ---
def get_clipboard():
    try:
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text
    except Exception:
        return ""

def set_clipboard(text):
    try:
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
    except Exception as e:
        print("Clipboard error:", e)

# --- BACKGROUND WEB SEARCH UTILITIES ---
def perform_search(query):
    try:
        data = urllib.parse.urlencode({'q': query}).encode('utf-8')
        req = urllib.request.Request(
            'https://lite.duckduckgo.com/lite/',
            data=data,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            page = response.read().decode('utf-8')
        
        raw_snippets = re.findall(
            r"class=[\x22\x27]result-snippet[\x22\x27][^>]*>(.*?)</td>",
            page,
            re.DOTALL
        )
        
        cleaned_snippets = []
        for s in raw_snippets[:4]:  # Top 4 results
            text = re.sub(r'<[^>]+>', '', s)
            text = html.unescape(text)
            text = text.strip()
            if text:
                cleaned_snippets.append(text)
                
        return "\n".join(cleaned_snippets)
    except Exception as e:
        print("Search error:", e)
        return ""

# --- SCREEN AWARENESS UTILITIES ---
def clean_for_speech(text):
    # Remove markdown bold/italic asterisks, backticks, hashtags, hyphens
    cleaned = re.sub(r'[*#`_\-~]', '', text)
    # Replace multiple spaces/newlines with a single space
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def capture_screen():
    try:
        folder = "Screenshots"
        if not os.path.exists(folder):
            os.makedirs(folder)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(folder, f"screenshot_{timestamp}.png")
        with mss.MSS() as sct:
            sct.shot(output=filename)
        print(f"[Screen Awareness] Screenshot captured: {filename}")
        return filename
    except Exception as e:
        print(f"[Screen Awareness] Error capturing screenshot: {e}")
        return None

def analyze_screen(prompt):
    screenshot_path = capture_screen()
    if not screenshot_path:
        return "Failed to capture screenshot, sir.", None
    
    print(f"[Screen Awareness] Analyzing screenshot with qwen2.5vl:3b...")
    
    def call_ollama():
        response = ollama.chat(
            model="qwen2.5vl:3b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [screenshot_path]
                }
            ]
        )
        return response["message"]["content"]

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(call_ollama)
            analysis = future.result(timeout=60)
        return analysis, screenshot_path
    except concurrent.futures.TimeoutError:
        print("[Screen Awareness] Analysis timed out after 60 seconds.")
        return "The screen analysis timed out, sir.", screenshot_path
    except Exception as e:
        print(f"[Screen Awareness] Analysis error: {e}")
        return f"I encountered an error during screen analysis, sir. {e}", screenshot_path

def save_analysis(analysis_text, screenshot_path):
    try:
        folder = "ScreenAnalysis"
        if not os.path.exists(folder):
            os.makedirs(folder)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(folder, f"analysis_{timestamp}.txt")
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"Screen Analysis Report - {timestamp}\n")
            f.write(f"Screenshot Path: {screenshot_path}\n")
            f.write("="*40 + "\n\n")
            f.write(analysis_text)
            
        print(f"[Screen Awareness] Analysis saved to {filename}")
        return filename
    except Exception as e:
        print(f"[Screen Awareness] Error saving analysis: {e}")
        return None

def screen_command_handler(user_lower):
    global latest_analysis
    
    # Describe screen commands
    if (
        "what's on my screen" in user_lower
        or "read my screen" in user_lower
        or "describe screen" in user_lower
        or "describe this page" in user_lower
        or "explain what i'm looking at" in user_lower
        or "explain what im looking at" in user_lower
    ):
        prompt = "Describe everything visible on this screen in a concise and useful way."
        speak("Analyzing your screen, sir. Please hold.")
        analysis, screenshot_path = analyze_screen(prompt)
        latest_analysis = {"text": analysis, "screenshot": screenshot_path}
        print(f"\nJarvis (Screen Analysis):\n{analysis}")
        speak(clean_for_speech(analysis))
        return True

    # Error analysis commands
    if (
        "analyze this error" in user_lower
        or "what error is this" in user_lower
        or "help me fix this" in user_lower
        or "what error is shown" in user_lower
        or "help me solve this error" in user_lower
    ):
        prompt = "Analyze this screenshot and explain any visible errors, warnings, exceptions, stack traces, compiler errors, terminal errors, IDE errors, or browser errors. Suggest fixes."
        speak("Analyzing the error on your screen, sir.")
        analysis, screenshot_path = analyze_screen(prompt)
        latest_analysis = {"text": analysis, "screenshot": screenshot_path}
        print(f"\nJarvis (Error Analysis):\n{analysis}")
        speak(clean_for_speech(analysis))
        return True

    # Coding assistant commands
    if (
        "explain this code" in user_lower
        or "review this code" in user_lower
    ):
        prompt = "Analyze visible source code and explain what it does. Identify bugs and improvements."
        speak("Reviewing the code on your screen, sir.")
        analysis, screenshot_path = analyze_screen(prompt)
        latest_analysis = {"text": analysis, "screenshot": screenshot_path}
        print(f"\nJarvis (Code Review):\n{analysis}")
        speak(clean_for_speech(analysis))
        return True

    # Document summary commands
    if (
        "read this document" in user_lower
        or "summarize this page" in user_lower
        or "summarize this document" in user_lower
    ):
        prompt = "Read all visible text and provide a concise summary."
        speak("Reading and summarizing the document, sir.")
        analysis, screenshot_path = analyze_screen(prompt)
        latest_analysis = {"text": analysis, "screenshot": screenshot_path}
        print(f"\nJarvis (Document Summary):\n{analysis}")
        speak(clean_for_speech(analysis))
        return True

    # Save screen analysis command
    if "save screen analysis" in user_lower or "save the analysis" in user_lower:
        if latest_analysis["text"] and latest_analysis["screenshot"]:
            filepath = save_analysis(latest_analysis["text"], latest_analysis["screenshot"])
            if filepath:
                speak(f"Screen analysis saved successfully, sir.")
            else:
                speak("I failed to save the analysis, sir.")
        else:
            speak("There is no recent screen analysis to save, sir.")
        return True

    return False

# --- AUDIO & VOICE UTILITIES ---
def speak(text):
    print(f"\nJarvis: {text}")

    text = text.encode(
        "ascii",
        errors="ignore"
    ).decode().strip()

    if not text:
        return

    result = subprocess.run(
        [PIPER, "-m", VOICE, "-f", "response.wav"],
        input=text,
        text=True,
        encoding="utf-8",
        capture_output=True
    )

    if result.returncode != 0:
        print(result.stderr)
        return

    subprocess.run([
        "powershell",
        "-c",
        "(New-Object Media.SoundPlayer 'response.wav').PlaySync();"
    ])

def record_audio(filename, seconds):
    fs = 16000
    recording = sd.rec(
        int(seconds * fs),
        samplerate=fs,
        channels=1,
        dtype="int16"
    )
    sd.wait()
    write(filename, fs, recording)

def wait_for_wake_word():
    print("\nSleeping...")
    print("Say: I'm back")

    while True:
        record_audio("wake.wav", 2)

        segments, _ = wake_model.transcribe(
            "wake.wav",
             language = "en"
        )

        text = " ".join(
            segment.text
            for segment in segments
        ).lower().strip()

        if text:
            print("Heard:", text)

        if any(
            phrase in text
            for phrase in WAKE_PHRASES
        ):
            print("Wake phrase detected.")
            speak(
                "Systems online, sir. Awaiting instructions."
            )
            return

def listen_command():
    print("\nListening...")
    record_audio("command.wav", 5)

    print("Transcribing...")
    segments, _ = command_model.transcribe(
        "command.wav",
        language="en"
    )

    text = " ".join(
        segment.text
        for segment in segments
    )

    return text.strip()

def get_volume():
    speakers = AudioUtilities.GetSpeakers()
    return speakers.EndpointVolume

print("\nJARVIS READY")

while True:
    wait_for_wake_word()

    while True:
        user = listen_command()
        print("\nYou said:", user)

        if not user:
            continue

        user_lower = user.lower()
        print("DEBUG:", repr(user_lower))

        # --- SLEEP COMMANDS ---

        if "go to sleep" in user_lower:
            speak("Goodbye sir, Entering standby mode.")
            break

        if (
            "thank you bye" in user_lower
            or "goodbye" in user_lower
            or "bye jarvis" in user_lower
        ):
            speak("Goodbye sir. Entering standby mode.")
            break

        if (
            "thank you" in user_lower
            or "thanks" in user_lower
        ):
            speak("You're welcome, sir.")
            continue

        # --- PERSISTENT MEMORY COMMANDS ---

        if user_lower.startswith("remember that ") or user_lower.startswith("remember "):
            fact = user
            if fact.lower().startswith("remember that "):
                fact = fact[14:]
            elif fact.lower().startswith("remember "):
                fact = fact[9:]
            fact = fact.strip()
            
            if fact:
                memory_data = load_memory()
                memory_data["facts"].append(fact)
                save_memory(memory_data)
                speak(f"I will remember that, sir.")
            else:
                speak("I didn't catch the fact to remember, sir.")
            continue

        if "what do you remember" in user_lower or "recall memory" in user_lower:
            memory_data = load_memory()
            facts = memory_data.get("facts", [])
            if facts:
                speak("Here is what I remember about you, sir:")
                for fact in facts:
                    speak(fact)
            else:
                speak("I don't have any facts stored in my memory, sir.")
            continue

        if "forget everything" in user_lower or "clear your memory" in user_lower or "clear memory" in user_lower:
            save_memory({"facts": []})
            speak("I have cleared my memory, sir.")
            continue

        # --- SCREEN AWARENESS COMMANDS ---
        if screen_command_handler(user_lower):
            continue

        # --- CLIPBOARD COMMANDS ---

        if (
            "read my clipboard" in user_lower
            or "read clipboard" in user_lower
            or "what is on my clipboard" in user_lower
            or "what's on my clipboard" in user_lower
        ):
            clip_text = get_clipboard()
            if clip_text:
                speak("Your clipboard contains: " + clip_text)
            else:
                speak("Your clipboard is empty, sir.")
            continue

        if (
            "summarize my clipboard" in user_lower
            or "summarize clipboard" in user_lower
            or "explain my clipboard" in user_lower
            or "explain clipboard" in user_lower
        ):
            clip_text = get_clipboard()
            if clip_text:
                speak("Summarizing clipboard contents, sir.")
                prompt = f"Summarize the following text from the user's clipboard in a concise, conversational manner (1-2 sentences):\n\n{clip_text}"
                current_sys = get_system_prompt()
                response = ollama.chat(
                    model="qwen3.5:4b",
                    messages=[
                        {"role": "system", "content": current_sys},
                        {"role": "user", "content": prompt}
                    ]
                )
                reply = response["message"]["content"]
                speak(reply)
            else:
                speak("Your clipboard is empty, sir.")
            continue

        if (
            "copy to clipboard" in user_lower
            or "write to clipboard" in user_lower
            or ("put" in user_lower and "on my clipboard" in user_lower)
        ):
            text_to_copy = user
            for phrase in ["copy to clipboard", "write to clipboard", "put", "on my clipboard"]:
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                text_to_copy = pattern.sub("", text_to_copy)
            text_to_copy = text_to_copy.strip()
            
            if text_to_copy:
                set_clipboard(text_to_copy)
                speak(f"I have copied '{text_to_copy}' to your clipboard, sir.")
            else:
                speak("There was no text specified to copy, sir.")
            continue

        # --- WEBSITES (Checks above App Launchers to avoid interception) ---

        if "youtube" in user_lower:
            webbrowser.open("https://youtube.com")
            speak("Opening YouTube")
            continue

        if "gmail" in user_lower:
            webbrowser.open("https://mail.google.com")
            speak("Opening Gmail")
            continue

        if "whatsapp" in user_lower:
            webbrowser.open("https://web.whatsapp.com")
            speak("Opening WhatsApp")
            continue

        if "chat gpt" in user_lower or "chatgpt" in user_lower:
            webbrowser.open("https://chatgpt.com")
            speak("Opening Chat GPT")
            continue

        if "google" in user_lower and "search" not in user_lower:
            webbrowser.open("https://google.com")
            speak("Opening Google")
            continue

        # --- WEB SEARCH AGENT (Background Search + AI Summary) ---

        if (
            "search the web for" in user_lower
            or "look up" in user_lower
            or "ask the web" in user_lower
            or user_lower.startswith("what is")
            or user_lower.startswith("who is")
            or user_lower.startswith("tell me about")
        ):
            query = user
            for phrase in ["search the web for", "search the web", "look up", "ask the web", "tell me about"]:
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                query = pattern.sub("", query)
            query = query.strip()
            
            if query:
                speak(f"Searching the web for {query}, sir...")
                search_results = perform_search(query)
                if search_results:
                    prompt = f"The user is asking: '{query}'. Synthesize a highly concise, direct answer (1-2 sentences) based on these search snippets:\n\n{search_results}"
                    current_sys = get_system_prompt()
                    response = ollama.chat(
                        model="qwen3.5:4b",
                        messages=[
                            {"role": "system", "content": current_sys},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    reply = response["message"]["content"]
                    speak(reply)
                else:
                    speak("I could not find any information on the web, sir.")
            else:
                speak("I could not determine the search query, sir.")
            continue

        # --- APP LAUNCHERS ---

        if user_lower.startswith("open "):
            app_name = (
                user_lower
                .replace("open ", "")
                .replace(".", "")
                .strip()
            )

            found = None
            for app in INSTALLED_APPS:
                if app_name in app["Name"].lower():
                    found = app
                    break

            if found:
                print(f"Launching: {found['Name']}")
                speak(f"Opening {found['Name']}, sir.")

                try:
                    subprocess.run(
                        [
                            "explorer.exe",
                            f"shell:AppsFolder\\{found['AppID']}"
                        ]
                    )
                except Exception as e:
                    print(e)
                    speak("Failed to launch application, sir.")
            else:
                speak("Application not found, sir.")

            continue

        # --- SYSTEM OPERATIONS ---

        if "lock computer" in user_lower:
            os.system("rundll32.exe user32.dll,LockWorkStation")
            continue

        if "shutdown computer" in user_lower:
            speak("Shutting down computer.")
            os.system("shutdown /s /t 5")
            continue

        if "restart computer" in user_lower:
            speak("Restarting computer.")
            os.system("shutdown /r /t 5")
            continue

        # --- BROWSER GOOGLE SEARCH ---

        if "search" in user_lower:
            query = user_lower
            query = query.replace("open google and search for", "")
            query = query.replace("search google for", "")
            query = query.replace("search for", "")
            query = query.replace("google search", "")
            query = query.strip()

            if query:
                webbrowser.open(f"https://www.google.com/search?q={query}")
                speak(f"Searching Google for {query}")
                continue

        # --- BATTERY ---

        if "battery" in user_lower:
            battery = psutil.sensors_battery()
            if battery:
                percent = battery.percent
                speak(f"Battery is at {percent} percent, sir.")
            else:
                speak("Battery information is unavailable, sir.")
            continue

        # --- TIME ---

        if "time" in user_lower:
            current_time = datetime.now().strftime("%I:%M %p")
            speak(f"The time is {current_time}, sir.")
            continue

        # --- DATE ---

        if "date" in user_lower:
            today = datetime.now().strftime("%d %B %Y")
            speak(f"Today is {today}, sir.")
            continue

        # --- SCREENSHOT ---

        if "screenshot" in user_lower:
            try:
                folder = "Screenshots"
                if not os.path.exists(folder):
                    os.makedirs(folder)

                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = os.path.join(folder, f"screenshot_{timestamp}.png")

                with mss.MSS() as sct:
                    sct.shot(output=filename)

                print(f"\nScreenshot saved to: {filename}")
                speak("Screenshot captured, sir.")
            except Exception as e:
                print(e)
                speak("Screenshot failed, sir.")
            continue

        # --- RAM ---

        if "ram" in user_lower or "memory" in user_lower:
            ram = psutil.virtual_memory()
            used = round(ram.used / (1024**3), 1)
            total = round(ram.total / (1024**3), 1)
            speak(f"RAM usage is {used} gigabytes out of {total} gigabytes, sir.")
            continue

        # --- CPU ---

        if "cpu" in user_lower or "processor" in user_lower:
            cpu = psutil.cpu_percent(interval=1)
            speak(f"CPU usage is {cpu} percent, sir.")
            continue

        # --- VOLUME CONTROL ---

        if "volume up" in user_lower:
            volume = get_volume()
            current = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(min(current + 0.1, 1.0), None)
            speak("Volume increased, sir.")
            continue

        if "volume down" in user_lower:
            volume = get_volume()
            current = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(max(current - 0.1, 0.0), None)
            speak("Volume decreased, sir.")
            continue

        if "mute" in user_lower:
            volume = get_volume()
            volume.SetMute(1, None)
            speak("Audio muted, sir.")
            continue

        if "unmute" in user_lower:
            volume = get_volume()
            volume.SetMute(0, None)
            speak("Audio restored, sir.")
            continue

        if "set volume to" in user_lower:
            try:
                import re
                match = re.search(r"(\d+)", user_lower)
                if match:
                    percent = int(match.group(1))
                    percent = max(0, min(percent, 100))
                    volume = get_volume()
                    volume.SetMasterVolumeLevelScalar(percent / 100, None)
                    speak(f"Volume set to {percent} percent, sir.")
                else:
                    speak("I could not determine the volume level, sir.")
            except Exception as e:
                print(e)
                speak("Volume adjustment failed, sir.")
            continue

        # --- PLAYBACK CONTROLS ---

        if (
            "play music" in user_lower
            or "pause music" in user_lower
            or "play pause" in user_lower
        ):
            keyboard.send("play/pause media")
            speak("Media toggled, sir.")
            continue

        if (
            "next song" in user_lower
            or "skip song" in user_lower
            or "next track" in user_lower
        ):
            keyboard.send("next track")
            speak("Skipping track, sir.")
            continue

        if (
            "previous song" in user_lower
            or "last song" in user_lower
            or "previous track" in user_lower
        ):
            keyboard.send("previous track")
            speak("Returning to previous track, sir.")
            continue

        if "stop music" in user_lower:
            keyboard.send("play/pause media")
            speak("Stopping playback, sir.")
            continue

        # --- AI CHAT FALLBACK (Rolling Session History + Persistent Memory Injection) ---

        # Add user query to conversation memory
        chat_history.append({"role": "user", "content": user})
        if len(chat_history) > 10:
            chat_history = chat_history[-10:]

        current_sys = get_system_prompt()
        messages = [{"role": "system", "content": current_sys}] + chat_history

        response = ollama.chat(
            model="qwen3.5:4b",
            messages=messages
        )

        reply = response["message"]["content"]
        
        # Save response to conversation memory
        chat_history.append({"role": "assistant", "content": reply})

        print("\nJarvis:", reply)
        speak(reply)