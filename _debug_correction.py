from speech_correction import correct, CORRECTIONS

text = "open calculator"
print(f"Input: {text!r}")
for wrong, right in CORRECTIONS.items():
    if wrong.lower() in text.lower():
        print(f"  Match: {wrong!r} -> {right!r}")
        print(f"  After replace: {text.lower().replace(wrong.lower(), right)!r}")
result = correct(text)
print(f"Result: {result!r}")
