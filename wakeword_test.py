from openwakeword.model import Model
import sounddevice as sd
import numpy as np

print("Loading OpenWakeWord...")

model = Model(inference_framework="onnx")

print("Loaded!")
print("Listening for wake words...")

THRESHOLD = 0.5

def callback(indata, frames, time, status):
    audio = np.frombuffer(indata, dtype=np.int16)

    prediction = model.predict(audio)

    for wakeword, score in prediction.items():
        if score > THRESHOLD:
            print(f"\nWAKE WORD DETECTED: {wakeword}")
            print(f"Score: {score:.3f}")

with sd.RawInputStream(
    samplerate=16000,
    blocksize=1280,
    dtype="int16",
    channels=1,
    callback=callback,
):
    while True:
        pass