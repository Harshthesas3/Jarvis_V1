from pathlib import Path
import ast

path = Path(r"C:\Jarvis\src\jarvis\skills\calendar.py")
lines = path.read_text(encoding="utf-8").splitlines()
for i, line in enumerate(lines):
    if 'kwargs["end_time"].replace' in line and "isoformat()" in line:
        lines[i] = (
            '                        event["end_time"] = datetime.fromisoformat('
            'kwargs["end_time"].replace("Z", "+00:00")).isoformat()'
        )
        print(f"fixed line {i + 1}")
text = "\n".join(lines) + "\n"
ast.parse(text)
path.write_text(text, encoding="utf-8")
print("calendar.py parse ok")
