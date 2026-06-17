"""
code_generator.py
-----------------
Generates code via Ollama. Takes a natural-language description and
returns the generated code as a string. Includes syntax validation
for common languages and an option to write generated code to a file.

Public API:
    generate_code(description: str, language: str = "") -> dict
    validate_syntax(code: str, language: str) -> tuple[bool, str]
    write_code_to_file(code: str, path: str) -> dict
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import subprocess

logger = logging.getLogger("jarvis.codegen")


def generate_code(description: str, language: str = "") -> dict:
    if not description:
        return {"ok": False, "tts": "No description provided, sir.", "code": ""}
    try:
        import ollama
    except ImportError as exc:
        return {"ok": False,
                "tts": "Code generation requires Ollama, which is not available, sir.",
                "code": ""}
    lang_hint = f" in {language}" if language else ""
    prompt = (
        f"Generate {description}{lang_hint}. "
        "Output ONLY the code block with no explanation, no markdown wrapping."
    )
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            fut = pool.submit(ollama.chat,
                              model="qwen3.5:4b",
                              messages=[{"role": "user", "content": prompt}],
                              options={"temperature": 0.2, "num_predict": 1024})
            resp = fut.result(timeout=45)  # timeout after 45s
        raw = resp["message"]["content"]
    except concurrent.futures.TimeoutError:
        logger.error("Ollama timed out after 45s")
        return {"ok": False, "tts": "Code generation timed out, sir.", "code": ""}
    except Exception as exc:
        logger.exception("code generation failed")
        return {"ok": False,
                "tts": f"Code generation failed, sir. {exc}",
                "code": ""}
    code = _extract_code(raw) or raw

    # Validate syntax if we know the language
    if language:
        valid, error_msg = validate_syntax(code, language)
        if not valid:
            logger.warning("Generated code has syntax issues: %s", error_msg)
    return {"ok": True,
            "tts": "Code generated, sir.",
            "code": code,
            "raw": raw,
            "language": language}


def write_code_to_file(code: str, path: str) -> dict:
    try:
        resolved = os.path.abspath(os.path.expanduser(path))
        parent = os.path.dirname(resolved)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(code)
        logger.info("Wrote code to %s (%d bytes)", resolved, len(code))
        return {"ok": True, "path": resolved, "bytes": len(code),
                "tts": f"Code written to {os.path.basename(resolved)}, sir."}
    except Exception as exc:
        logger.exception("Failed to write code to %s", path)
        return {"ok": False, "tts": f"Failed to write code, sir. {exc}"}


def validate_syntax(code: str, language: str) -> tuple[bool, str]:
    lang = language.lower().strip()
    if lang == "python":
        try:
            compile(code, "<generated>", "exec")
            return True, ""
        except SyntaxError as e:
            return False, f"Python syntax error: {e}"
    elif lang in ("javascript", "js"):
        try:
            result = subprocess.run(
                ["node", "--check", "-"],
                input=code,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip()
        except FileNotFoundError:
            pass
    elif lang in ("json",):
        try:
            json.loads(code)
            return True, ""
        except json.JSONDecodeError as e:
            return False, f"JSON parse error: {e}"
    return True, ""


def _extract_code(text: str) -> str | None:
    m = re.search(r"```(?:\w+)?\n([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    return None
