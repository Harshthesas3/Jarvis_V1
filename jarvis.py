import ollama
import subprocess

PIPER = r"C:\Users\Harshith\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\Scripts\piper.exe"

VOICE = r"C:\Users\Harshith\Downloads\en_US-lessac-medium.onnx"


def speak(text):
    # Remove emojis and unsupported characters
    text = text.encode("ascii", errors="ignore").decode()

    subprocess.run(
        [PIPER, "-m", VOICE, "-f", "response.wav"],
        input=text,
        text=True,
        encoding="utf-8"
    )

    subprocess.run([
        "powershell",
        "-c",
        "(New-Object Media.SoundPlayer 'response.wav').PlaySync();"
    ])


SYSTEM_PROMPT = """
You are Jarvis.

Rules:
- Never use emojis.
- Never use markdown.
- Never use bullet points unless asked.
- Speak naturally like an intelligent AI assistant.
- Keep answers concise unless asked for details.
"""


print("Jarvis Online")
print("Type 'exit' to quit.\n")

while True:
    user = input("You: ")

    if user.lower() in ["exit", "quit"]:
        print("Shutting down...")
        break

    try:
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

    except Exception as e:
        print(f"\nError: {e}\n")