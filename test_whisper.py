from faster_whisper import WhisperModel

print("Loading...")

model = WhisperModel("tiny", device="cpu", compute_type="int8")

print("Loaded!")