"""
file_manager.py
---------------
File and folder operations for JARVIS. All operations are sandboxed to a
small set of safe root directories (the user's home, the current working
directory, and the system temp folder). Operations against blocked paths
(C:\\Windows, C:\\Program Files*, etc.) are rejected before any side effect.

Public API:
    list_ops() -> list[str]
    run(op: str, **params) -> dict

The returned dict has shape:
    {"ok": bool, "tts": str, "op": str, "data": dict}

Design notes:
- Uses pathlib throughout.
- "Open" launches the OS handler (os.startfile on Windows; xdg-open elsewhere).
- Search walks the sandboxed root and matches names (case-insensitive) OR
  file contents (text files only) containing the query.
- All operations log to "jarvis.files".
- All operations are designed to never raise into the executor.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("jarvis.files")

# ---------------------------------------------------------------------------
# Sandbox configuration
# ---------------------------------------------------------------------------
_HOME = Path(os.path.expanduser("~")).resolve()
_CWD = Path(os.getcwd()).resolve()
_TEMP = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp").resolve()

_ALLOWED_ROOTS: list[Path] = [
    _HOME, _CWD, _TEMP,
]

# Block roots - even if they happen to be under an allowed root (e.g.
# C:\\Windows is never under a user home, but we double-check anyway).
_BLOCKED_SUBSTRINGS = (
    os.path.join(os.sep, "Windows"),
    os.path.join(os.sep, "Program Files"),
    os.path.join(os.sep, "Program Files (x86)"),
    os.path.join(os.sep, "ProgramData"),
    os.path.join(os.sep, "System32"),
    os.path.join(os.sep, "SysWOW64"),
    os.path.join(os.sep, "Boot"),
)

# Hard limits to keep voice-driven ops from running away.
_MAX_SEARCH_RESULTS = 25
_MAX_FILE_BYTES_FOR_CONTENT_SEARCH = 5 * 1024 * 1024  # 5 MB
_MAX_READ_BYTES = 200_000  # Read will truncate beyond this for TTS safety

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _norm(path_like) -> Path:
    """Resolve a user-supplied path to an absolute Path. Empty -> CWD."""
    if not path_like:
        return _CWD
    p = Path(os.path.expandvars(os.path.expanduser(str(path_like))))
    try:
        return p.resolve()
    except Exception:
        # resolve() can fail on broken symlinks. Fall back to absolute.
        return Path(os.path.abspath(str(p)))


def _is_blocked(p: Path) -> bool:
    s = str(p)
    return any(blocked in s for blocked in _BLOCKED_SUBSTRINGS)


def _is_under_allowed_root(p: Path) -> bool:
    if _is_blocked(p):
        return False
    for root in _ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _validate_inside_sandbox(p: Path, *, must_exist: bool):
    if not str(p):
        return False, "Empty path, sir."
    if not _is_under_allowed_root(p):
        return False, (
            f"Refusing to touch {p}, sir. That path is outside the allowed "
            f"sandbox or is a protected system folder."
        )
    if must_exist and not p.exists():
        return False, f"I could not find {p.name}, sir."
    return True, ""


# ---------------------------------------------------------------------------
# Public: list_ops
# ---------------------------------------------------------------------------
def list_ops() -> list[str]:
    return [
        # File ops
        "create_file", "read_file", "write_file", "append_file", "delete_file",
        "rename_file", "move_file", "copy_file", "search_files", "open_file",
        # Folder ops
        "create_folder", "delete_folder", "rename_folder", "list_folder",
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_tts(text: str, limit: int = 400) -> str:
    if text is None:
        return ""
    text = str(text).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "... (truncated)"
    return text


def _open_with_os(path: Path) -> bool:
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not open %s: %s", path, exc)
        return False


def _confirm_default(prompt: str) -> bool:
    try:
        ans = input(f"\n{prompt} [y/N]: ").strip().lower()
        return ans in ("y", "yes")
    except EOFError:
        return False


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------
def _op_create_file(name: str, content: str = "", folder: str = "") -> dict:
    base = _norm(folder) if folder else _CWD
    ok, err = _validate_inside_sandbox(base, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "create_file", "data": {}}
    target = (base / name).resolve()
    ok, err = _validate_inside_sandbox(target, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "create_file", "data": {}}
    if target.exists():
        return {"ok": False,
                "tts": f"{target.name} already exists, sir.",
                "op": "create_file", "data": {}}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_file failed")
        return {"ok": False,
                "tts": f"Failed to create {name}, sir. {exc}",
                "op": "create_file", "data": {}}
    return {"ok": True,
            "tts": f"Created {target.name}, sir.",
            "op": "create_file",
            "data": {"path": str(target)}}


def _op_read_file(path: str) -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "read_file", "data": {}}
    if not p.is_file():
        return {"ok": False,
                "tts": f"{p.name} is not a file, sir.",
                "op": "read_file", "data": {}}
    try:
        size = p.stat().st_size
        if size > _MAX_READ_BYTES:
            text = p.read_text(encoding="utf-8", errors="ignore")[:_MAX_READ_BYTES]
            return {"ok": True,
                    "tts": _to_tts(text),
                    "op": "read_file",
                    "data": {"path": str(p), "truncated": True, "size": size}}
        text = p.read_text(encoding="utf-8", errors="ignore")
        return {"ok": True,
                "tts": _to_tts(text) if text else f"{p.name} is empty, sir.",
                "op": "read_file",
                "data": {"path": str(p), "size": size}}
    except Exception as exc:  # noqa: BLE001
        logger.exception("read_file failed")
        return {"ok": False,
                "tts": f"Failed to read {p.name}, sir. {exc}",
                "op": "read_file", "data": {}}


def _op_delete_file(path: str, confirm_fn: Optional[Callable[[str], bool]] = None) -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "delete_file", "data": {}}
    if not p.is_file():
        return {"ok": False,
                "tts": f"{p.name} is not a file, sir.",
                "op": "delete_file", "data": {}}
    confirm = confirm_fn or _confirm_default
    if not confirm(f"Delete file {p}? (yes/no)"):
        return {"ok": False, "cancelled": True,
                "tts": "Delete cancelled, sir.",
                "op": "delete_file", "data": {}}
    try:
        p.unlink()
    except Exception as exc:  # noqa: BLE001
        logger.exception("delete_file failed")
        return {"ok": False,
                "tts": f"Failed to delete {p.name}, sir. {exc}",
                "op": "delete_file", "data": {}}
    return {"ok": True,
            "tts": f"Deleted {p.name}, sir.",
            "op": "delete_file",
            "data": {"path": str(p)}}


def _op_rename_file(path: str, new_name: str = "") -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "rename_file", "data": {}}
    if not new_name or "/" in new_name or "\\" in new_name:
        return {"ok": False,
                "tts": "New name must be a plain filename, sir.",
                "op": "rename_file", "data": {}}
    target = (p.parent / new_name).resolve()
    ok, err = _validate_inside_sandbox(target, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "rename_file", "data": {}}
    if target.exists():
        return {"ok": False,
                "tts": f"{new_name} already exists, sir.",
                "op": "rename_file", "data": {}}
    try:
        p.rename(target)
    except Exception as exc:  # noqa: BLE001
        logger.exception("rename_file failed")
        return {"ok": False,
                "tts": f"Failed to rename, sir. {exc}",
                "op": "rename_file", "data": {}}
    return {"ok": True,
            "tts": f"Renamed to {new_name}, sir.",
            "op": "rename_file",
            "data": {"from": str(p), "to": str(target)}}


def _op_move_file(path: str, dest_folder: str = "") -> dict:
    p = _norm(path)
    dest = _norm(dest_folder)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "move_file", "data": {}}
    ok, err = _validate_inside_sandbox(dest, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "move_file", "data": {}}
    if not dest.is_dir():
        return {"ok": False,
                "tts": f"{dest} is not a folder, sir.",
                "op": "move_file", "data": {}}
    try:
        dest.mkdir(parents=True, exist_ok=True)
        target = (dest / p.name).resolve()
        if target.exists():
            return {"ok": False,
                    "tts": f"{p.name} already exists in {dest.name}, sir.",
                    "op": "move_file", "data": {}}
        shutil.move(str(p), str(dest))
    except Exception as exc:  # noqa: BLE001
        logger.exception("move_file failed")
        return {"ok": False,
                "tts": f"Failed to move {p.name}, sir. {exc}",
                "op": "move_file", "data": {}}
    return {"ok": True,
            "tts": f"Moved {p.name} to {dest.name}, sir.",
            "op": "move_file",
            "data": {"from": str(p), "to": str(dest)}}


def _op_copy_file(path: str, dest_folder: str = "") -> dict:
    p = _norm(path)
    dest = _norm(dest_folder)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "copy_file", "data": {}}
    ok, err = _validate_inside_sandbox(dest, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "copy_file", "data": {}}
    if not dest.is_dir():
        return {"ok": False,
                "tts": f"{dest} is not a folder, sir.",
                "op": "copy_file", "data": {}}
    try:
        dest.mkdir(parents=True, exist_ok=True)
        target = (dest / p.name).resolve()
        ok, err = _validate_inside_sandbox(target, must_exist=False)
        if not ok:
            return {"ok": False, "tts": err, "op": "copy_file", "data": {}}
        shutil.copy2(str(p), str(target))
    except Exception as exc:  # noqa: BLE001
        logger.exception("copy_file failed")
        return {"ok": False,
                "tts": f"Failed to copy {p.name}, sir. {exc}",
                "op": "copy_file", "data": {}}
    return {"ok": True,
            "tts": f"Copied {p.name} to {dest.name}, sir.",
            "op": "copy_file",
            "data": {"from": str(p), "to": str(target)}}


def _op_search_files(query: str, folder: str = "") -> dict:
    if not query:
        return {"ok": False, "tts": "No search query, sir.",
                "op": "search_files", "data": {}}
    root = _norm(folder) if folder else _CWD
    ok, err = _validate_inside_sandbox(root, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "search_files", "data": {}}
    if not root.is_dir():
        return {"ok": False,
                "tts": f"{root} is not a folder, sir.",
                "op": "search_files", "data": {}}

    ql = query.lower()
    name_hits: list[str] = []
    content_hits: list[dict] = []
    skipped = 0

    try:
        for path, dirs, files in os.walk(root):
            # Don't descend into blocked system trees if they're under root.
            dirs[:] = [d for d in dirs
                       if not _is_blocked(Path(path) / d)]
            for fname in files:
                fp = Path(path) / fname
                if _is_blocked(fp):
                    continue
                if ql in fname.lower():
                    name_hits.append(str(fp))
                    if len(name_hits) >= _MAX_SEARCH_RESULTS:
                        break
                elif ql and not _is_blocked(fp) and fp.is_file():
                    try:
                        if fp.stat().st_size > _MAX_FILE_BYTES_FOR_CONTENT_SEARCH:
                            continue
                        if not _looks_like_text(fp):
                            continue
                        with fp.open("r", encoding="utf-8",
                                     errors="ignore") as f:
                            for ln, line in enumerate(f, 1):
                                if ql in line.lower():
                                    content_hits.append({
                                        "path": str(fp),
                                        "line": ln,
                                        "snippet": line.strip()[:200],
                                    })
                                    break
                            if len(content_hits) >= _MAX_SEARCH_RESULTS:
                                break
                    except (OSError, PermissionError):
                        skipped += 1
                        continue
            if (len(name_hits) >= _MAX_SEARCH_RESULTS
                    and len(content_hits) >= _MAX_SEARCH_RESULTS):
                break
    except Exception as exc:  # noqa: BLE001
        logger.exception("search_files walk failed")
        return {"ok": False,
                "tts": f"Search failed, sir. {exc}",
                "op": "search_files", "data": {}}

    if not name_hits and not content_hits:
        return {"ok": True,
                "tts": f"I could not find anything matching '{query}' under "
                       f"{root.name}, sir.",
                "op": "search_files",
                "data": {"query": query, "root": str(root),
                         "name_hits": [], "content_hits": []}}

    # Build a short TTS-friendly list, then attach the full result list
    # to `data` for the caller (UI / logs) to consume.
    preview = []
    for h in name_hits[:5]:
        preview.append(Path(h).name)
    for h in content_hits[:5]:
        preview.append(
            f"{Path(h['path']).name} (line {h['line']})"
        )
    tts = (
        f"I found {len(name_hits)} file name match"
        f"{'es' if len(name_hits) != 1 else ''} and "
        f"{len(content_hits)} content match"
        f"{'es' if len(content_hits) != 1 else ''} for '{query}', sir. "
        f"Top results: " + ", ".join(preview) + "."
    )
    return {"ok": True,
            "tts": tts,
            "op": "search_files",
            "data": {"query": query, "root": str(root),
                     "name_hits": name_hits, "content_hits": content_hits,
                     "skipped": skipped}}


def _looks_like_text(p: Path) -> bool:
    """Cheap heuristic: try to read the first 4 KB; if it contains a NUL
    byte in the first 1 KB, treat it as binary and skip."""
    try:
        with p.open("rb") as f:
            chunk = f.read(4096)
        return b"\x00" not in chunk[:1024]
    except Exception:
        return False


def _op_append_file(path: str, content: str = "") -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "append_file", "data": {}}
    if not p.is_file():
        return {"ok": False,
                "tts": f"{p.name} is not a file, sir.",
                "op": "append_file", "data": {}}
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(content or "")
    except Exception as exc:
        logger.exception("append_file failed")
        return {"ok": False,
                "tts": f"Failed to append to {p.name}, sir. {exc}",
                "op": "append_file", "data": {}}
    return {"ok": True,
            "tts": f"Appended to {p.name}, sir.",
            "op": "append_file",
            "data": {"path": str(p)}}


def _op_write_file(path: str, content: str = "") -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "write_file", "data": {}}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content or "", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.exception("write_file failed")
        return {"ok": False,
                "tts": f"Failed to write, sir. {exc}",
                "op": "write_file", "data": {}}
    return {"ok": True,
            "tts": f"Written to {p.name}, sir.",
            "op": "write_file",
            "data": {"path": str(p)}}


def _op_open_file(path: str) -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "open_file", "data": {}}
    if _open_with_os(p):
        return {"ok": True,
                "tts": f"Opening {p.name}, sir.",
                "op": "open_file",
                "data": {"path": str(p)}}
    return {"ok": False,
            "tts": f"Failed to open {p.name}, sir.",
            "op": "open_file",
            "data": {"path": str(p)}}


# ---------------------------------------------------------------------------
# Folder operations
# ---------------------------------------------------------------------------
def _op_create_folder(name: str, parent: str = "") -> dict:
    base = _norm(parent) if parent else _CWD
    ok, err = _validate_inside_sandbox(base, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "create_folder", "data": {}}
    target = (base / name).resolve()
    ok, err = _validate_inside_sandbox(target, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "create_folder", "data": {}}
    if target.exists():
        return {"ok": False,
                "tts": f"{target.name} already exists, sir.",
                "op": "create_folder", "data": {}}
    try:
        target.mkdir(parents=True, exist_ok=False)
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_folder failed")
        return {"ok": False,
                "tts": f"Failed to create folder, sir. {exc}",
                "op": "create_folder", "data": {}}
    return {"ok": True,
            "tts": f"Created folder {target.name}, sir.",
            "op": "create_folder",
            "data": {"path": str(target)}}


def _op_delete_folder(path: str, confirm_fn: Optional[Callable[[str], bool]] = None) -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "delete_folder", "data": {}}
    if not p.is_dir():
        return {"ok": False,
                "tts": f"{p.name} is not a folder, sir.",
                "op": "delete_folder", "data": {}}
    if p in _ALLOWED_ROOTS:
        return {"ok": False,
                "tts": "Refusing to delete a sandbox root, sir.",
                "op": "delete_folder", "data": {}}
    confirm = confirm_fn or _confirm_default
    if not confirm(f"Delete folder {p} and all its contents? (yes/no)"):
        return {"ok": False, "cancelled": True,
                "tts": "Delete folder cancelled, sir.",
                "op": "delete_folder", "data": {}}
    try:
        shutil.rmtree(str(p))
    except Exception as exc:  # noqa: BLE001
        logger.exception("delete_folder failed")
        return {"ok": False,
                "tts": f"Failed to delete folder, sir. {exc}",
                "op": "delete_folder", "data": {}}
    return {"ok": True,
            "tts": f"Deleted folder {p.name}, sir.",
            "op": "delete_folder",
            "data": {"path": str(p)}}


def _op_rename_folder(path: str, new_name: str = "") -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "rename_folder", "data": {}}
    if not p.is_dir():
        return {"ok": False,
                "tts": f"{p.name} is not a folder, sir.",
                "op": "rename_folder", "data": {}}
    if not new_name or "/" in new_name or "\\" in new_name:
        return {"ok": False,
                "tts": "New name must be a plain folder name, sir.",
                "op": "rename_folder", "data": {}}
    target = (p.parent / new_name).resolve()
    ok, err = _validate_inside_sandbox(target, must_exist=False)
    if not ok:
        return {"ok": False, "tts": err, "op": "rename_folder", "data": {}}
    if target.exists():
        return {"ok": False,
                "tts": f"{new_name} already exists, sir.",
                "op": "rename_folder", "data": {}}
    try:
        p.rename(target)
    except Exception as exc:
        logger.exception("rename_folder failed")
        return {"ok": False,
                "tts": f"Failed to rename folder, sir. {exc}",
                "op": "rename_folder", "data": {}}
    return {"ok": True,
            "tts": f"Renamed folder to {new_name}, sir.",
            "op": "rename_folder",
            "data": {"from": str(p), "to": str(target)}}


def _op_list_folder(path: str = "") -> dict:
    p = _norm(path)
    ok, err = _validate_inside_sandbox(p, must_exist=True)
    if not ok:
        return {"ok": False, "tts": err, "op": "list_folder", "data": {}}
    if not p.is_dir():
        return {"ok": False,
                "tts": f"{p.name} is not a folder, sir.",
                "op": "list_folder", "data": {}}
    try:
        entries = list(p.iterdir())
    except Exception as exc:  # noqa: BLE001
        logger.exception("list_folder failed")
        return {"ok": False,
                "tts": f"Failed to list folder, sir. {exc}",
                "op": "list_folder", "data": {}}

    entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
    folders = [e.name + ("/" if e.is_dir() else "") for e in entries if e.is_dir()]
    files = [e.name for e in entries if e.is_file()]
    if not folders and not files:
        return {"ok": True,
                "tts": f"{p.name} is empty, sir.",
                "op": "list_folder",
                "data": {"path": str(p), "folders": [], "files": []}}

    preview = folders[:5] + files[:5]
    return {"ok": True,
            "tts": (f"{p.name} contains "
                    f"{len(folders)} folder{'s' if len(folders) != 1 else ''} "
                    f"and {len(files)} file{'s' if len(files) != 1 else ''}, "
                    f"sir. Top entries: " + ", ".join(preview) + "."),
            "op": "list_folder",
            "data": {"path": str(p), "folders": folders, "files": files}}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
_OPS: dict = {
    "create_file":   _op_create_file,
    "read_file":     _op_read_file,
    "write_file":    _op_write_file,
    "append_file":   _op_append_file,
    "delete_file":   _op_delete_file,
    "rename_file":   _op_rename_file,
    "move_file":     _op_move_file,
    "copy_file":     _op_copy_file,
    "search_files":  _op_search_files,
    "open_file":     _op_open_file,
    "create_folder": _op_create_folder,
    "delete_folder": _op_delete_folder,
    "rename_folder": _op_rename_folder,
    "list_folder":   _op_list_folder,
}


def run(op: str, **params: Any) -> dict:
    """Dispatch a file/folder op. `op` is the canonical key, params depend
    on the op. Always returns a dict; never raises."""
    if not op:
        return {"ok": False, "tts": "No operation given, sir.",
                "op": "", "data": {}}
    handler = _OPS.get(op)
    if not handler:
        return {"ok": False,
                "tts": f"Unknown file operation '{op}', sir.",
                "op": op, "data": {}}
    logger.info("file_manager.run: op=%s params=%s", op,
                {k: v for k, v in params.items() if k != "confirm_fn"})
    try:
        return handler(**params)
    except Exception as exc:  # noqa: BLE001
        logger.exception("file_manager op failed: %s", op)
        return {"ok": False,
                "tts": f"File operation failed, sir. {exc}",
                "op": op, "data": {}}
