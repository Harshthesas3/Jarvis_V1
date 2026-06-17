import os
import ollama
import subprocess
import sounddevice as sd
from scipy.io.wavfile import write
from faster_whisper import WhisperModel

PIPER = r"C:\Users\Harshith\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\Scripts\piper.exe"
VOICE = r"C:\Users\Harshith\Downloads\en_US-lessac-medium.onnx"

print("Loading Whisper...")
model = WhisperModel("tiny", device="cpu", compute_type="int8")
print("Whisper loaded!")

SYSTEM_PROMPT = """
You are JARVIS.

Speak naturally and professionally.

Keep answers concise.

You are the personal AI assistant of Harshith.

Never use emojis.
Never use markdown.

When greeting Harshith, address him by name.

For technical questions provide accurate concise explanations.

For commands, assume they are intended for desktop control.
"""
def speak(text):
    text = text.encode("ascii", errors="ignore").decode().strip()

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

def listen(seconds=5):
    fs = 16000

    print("\nListening...")

    recording = sd.rec(
        int(seconds * fs),
        samplerate=fs,
        channels=1,
        dtype="int16"
    )

    sd.wait()

    write("input.wav", fs, recording)

    print("Transcribing...")

    segments, _ = model.transcribe("input.wav")

    text = " ".join(segment.text for segment in segments)

    return text.strip()

print("Jarvis Voice Mode")
print("Press ENTER and speak.")
print("Type exit to quit.\n")

while True:

    cmd = input("Press ENTER to talk (or type exit): ")

    if cmd.lower() == "exit":
        break

    user = listen()

    print(f"\nYou said: {user}")

    if not user:
        continue

    # APP COMMANDS

    if "open chrome" in user.lower():
        os.system("start chrome")
        speak("Opening Chrome")
        continue

    if "open downloads" in user.lower():
        os.startfile(r"C:\Users\Harshith\Downloads")
        speak("Opening Downloads")
        continue

    if "open notepad" in user.lower():
        os.system("start notepad")
        speak("Opening Notepad")
        continue

    if "open calculator" in user.lower():
        os.system("start calc")
        speak("Opening Calculator")
        continue

    # AI CHAT

    response = ollama.chat(
        model="qwen3.5:4b",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user
            }
        ]
    )

    reply = response["message"]["content"]

    print(f"\nJarvis: {reply}\n")

    speak(reply)