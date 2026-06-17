import sounddevice as sd
import numpy as np
import time

THRESHOLD = 3500
PEAK_RATIO = 4
COOLDOWN = 1.5

last_trigger = 0

print("Listening for claps...")

def callback(indata, frames, time_info, status):
    global last_trigger

    audio = np.frombuffer(indata, dtype=np.int16)

    peak = np.max(np.abs(audio))
    avg = np.mean(np.abs(audio))

    now = time.time()

    # Clap = sharp peak
    if peak > THRESHOLD and peak > avg * PEAK_RATIO:

        if now - last_trigger > COOLDOWN:
            print(f"\nCLAP DETECTED! Peak={peak} Avg={avg:.0f}")
            last_trigger = now

with sd.RawInputStream(
    samplerate=16000,
    blocksize=1024,
    dtype="int16",
    channels=1,
    callback=callback,
):
    while True:
        time.sleep(0.1)