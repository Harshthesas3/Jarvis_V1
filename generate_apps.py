import subprocess
import json

result = subprocess.check_output(
    [
        "powershell",
        "-Command",
        "Get-StartApps"
    ],
    text=True,
    encoding="utf-8",
    errors="ignore"
)

apps = {}

for line in result.splitlines():

    if len(line.strip()) < 5:
        continue

    if "----" in line:
        continue

    parts = line.split()

    if len(parts) < 2:
        continue

    app_name = " ".join(parts[:-1]).lower()

    apps[app_name] = line

with open(
    "apps.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        apps,
        f,
        indent=4
    )

print(
    f"Saved {len(apps)} apps."
)