"""File explorer skill implementation."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.skills.interfaces import SkillInterface

logger = logging.getLogger("jarvis.skills.explorer")


class ExplorerSkill(SkillInterface):
    """Skill for file system exploration and operations."""

    @property
    def name(self) -> str:
        return "explorer"

    @property
    def description(self) -> str:
        return "File system exploration including directory listing, file operations, and path resolution"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute file explorer operations.

        Supported operations:
        Supported operations:
        - list_directory: List contents of a directory
        - create_directory: Create a directory
        - delete_directory: Delete a directory
        - file_exists: Check if a file exists
        - directory_exists: Check if a directory exists
        - get_file_info: Get information about a file
        - get_directory_info: Get information about a directory
        - read_file: Read file contents
        - write_file: Write file contents
        - delete_file: Delete a file
        - copy_file: Copy a file
        - move_file: Move a file
        - resolve_path: Resolve a path to absolute form
        - search_files: Search for files by pattern

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary containing:
                - success (bool): Whether execution succeeded
                - reason (str): Human-readable reason for success/failure
                - logs (List[str]): Execution logs
                - data (Any): Operation-specific result data
                - execution_time (float): Time taken to execute
        """
        start_time = time.time()
        action = kwargs.get("action", "").lower()

        try:
            if action == "list_directory":
                result = self._list_directory(**kwargs)
            elif action == "create_directory":
                result = self._create_directory(**kwargs)
            elif action == "delete_directory":
                result = self._delete_directory(**kwargs)
            elif action == "file_exists":
                result = self._file_exists(**kwargs)
            elif action == "directory_exists":
                result = self._directory_exists(**kwargs)
            elif action == "get_file_info":
                result = self._get_file_info(**kwargs)
            elif action == "get_directory_info":
                result = self._get_directory_info(**kwargs)
            elif action == "read_file":
                result = self._read_file(**kwargs)
            elif action == "write_file":
                result = self._write_file(**kwargs)
            elif action == "delete_file":
                result = self._delete_file(**kwargs)
            elif action == "copy_file":
                result = self._copy_file(**kwargs)
            elif action == "move_file":
                result = self._move_file(**kwargs)
            elif action == "resolve_path":
                result = self._resolve_path(**kwargs)
            elif action == "search_files":
                result = self._search_files(**kwargs)
            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [
                        f"Available actions: list_directory, create_directory, delete_directory, file_exists, directory_exists, get_file_info, get_directory_info, read_file, write_file, delete_file, copy_file, move_file, resolve_path, search_files"
                    ],
                    "data": None
                }

            # Add execution time to result
            result["execution_time"] = time.time() - start_time
            return result

        except Exception as e:
            logger.error("ExplorerSkill execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "reason": f"ExplorerSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }

    def _list_directory(self, **kwargs) -> Dict[str, Any]:
        """List contents of a directory."""
        path = kwargs.get("path", ".")
        recursive = kwargs.get("recursive", False)
        include_hidden = kwargs.get("include_hidden", False)

        try:
            path_obj = Path(path).resolve()
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"Directory does not exist: {path}",
                    "logs": [f"Path not found: {path}"],
                    "data": None
                }

            if not path_obj.is_dir():
                return {
                    "success": False,
                    "reason": f"Path is not a directory: {path}",
                    "logs": [f"Path is a file, not directory: {path}"],
                    "data": None
                }

            items = []
            if recursive:
                for item in path_obj.rglob("*"):
                    if not include_hidden and any(part.startswith('.') for part in item.parts):
                        continue
                    items.append(str(item.relative_to(path_obj)))
            else:
                for item in path_obj.iterdir():
                    if not include_hidden and item.name.startswith('.'):
                        continue
                    items.append(item.name)

            return {
                "success": True,
                "reason": f"Listed {len(items)} items in {path}",
                "logs": [f"Directory listing: {path}", f"Found {len(items)} items"],
                "data": {
                    "path": str(path_obj),
                    "items": sorted(items),
                    "count": len(items)
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to list directory: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _create_directory(self, **kwargs) -> Dict[str, Any]:
        """Create a directory."""
        path = kwargs.get("path")
        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            path_obj.mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "reason": f"Directory created: {path}",
                "logs": [f"Created directory: {path}"],
                "data": {"path": str(path_obj.resolve())}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to create directory: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _delete_directory(self, **kwargs) -> Dict[str, Any]:
        """Delete a directory."""
        path = kwargs.get("path")
        recursive = kwargs.get("recursive", False)

        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"Directory does not exist: {path}",
                    "logs": [f"Path not found: {path}"],
                    "data": None
                }

            if not path_obj.is_dir():
                return {
                    "success": False,
                    "reason": f"Path is not a directory: {path}",
                    "logs": [f"Path is a file, not directory: {path}"],
                    "data": None
                }

            if recursive:
                import shutil
                shutil.rmtree(path_obj)
            else:
                path_obj.rmdir()  # Only works if empty

            return {
                "success": True,
                "reason": f"Directory deleted: {path}",
                "logs": [f"Deleted directory: {path}"],
                "data": {"path": str(path_obj.resolve())}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to delete directory: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _file_exists(self, **kwargs) -> Dict[str, Any]:
        """Check if a file exists."""
        path = kwargs.get("path")
        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            exists = path_obj.is_file()
            return {
                "success": True,
                "reason": f"File {'exists' if exists else 'does not exist'}: {path}",
                "logs": [f"File check: {path} -> {'exists' if exists else 'not found'}"],
                "data": {
                    "path": str(path_obj.resolve()),
                    "exists": exists,
                    "is_file": exists,
                    "is_directory": path_obj.is_dir()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to check file existence: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _directory_exists(self, **kwargs) -> Dict[str, Any]:
        """Check if a directory exists."""
        path = kwargs.get("path")
        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            exists = path_obj.is_dir()
            return {
                "success": True,
                "reason": f"Directory {'exists' if exists else 'does not exist'}: {path}",
                "logs": [f"Directory check: {path} -> {'exists' if exists else 'not found'}"],
                "data": {
                    "path": str(path_obj.resolve()),
                    "exists": exists,
                    "is_file": path_obj.is_file(),
                    "is_directory": exists
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to check directory existence: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _get_file_info(self, **kwargs) -> Dict[str, Any]:
        """Get information about a file."""
        path = kwargs.get("path")
        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"File does not exist: {path}",
                    "logs": [f"Path not found: {path}"],
                    "data": None
                }

            stat = path_obj.stat()
            return {
                "success": True,
                "reason": f"File info retrieved: {path}",
                "logs": [f"File stats: {path}"],
                "data": {
                    "path": str(path_obj.resolve()),
                    "name": path_obj.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "created": stat.st_ctime,
                    "is_file": path_obj.is_file(),
                    "is_directory": path_obj.is_dir(),
                    "extension": path_obj.suffix
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to get file info: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _get_directory_info(self, **kwargs) -> Dict[str, Any]:
        """Get information about a directory."""
        path = kwargs.get("path")
        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"Directory does not exist: {path}",
                    "logs": [f"Path not found: {path}"],
                    "data": None
                }

            if not path_obj.is_dir():
                return {
                    "success": False,
                    "reason": f"Path is not a directory: {path}",
                    "logs": [f"Path is a file, not directory: {path}"],
                    "data": None
                }

            # Count items
            try:
                items = list(path_obj.iterdir())
                file_count = sum(1 for item in items if item.is_file())
                dir_count = sum(1 for item in items if item.is_dir())
            except PermissionError:
                file_count = dir_count = -1  # Permission denied

            stat = path_obj.stat()
            return {
                "success": True,
                "reason": f"Directory info retrieved: {path}",
                "logs": [f"Directory stats: {path}"],
                "data": {
                    "path": str(path_obj.resolve()),
                    "name": path_obj.name,
                    "modified": stat.st_mtime,
                    "created": stat.st_ctime,
                    "file_count": file_count,
                    "directory_count": dir_count,
                    "total_items": len(items) if 'items' in locals() else -1
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to get directory info: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _read_file(self, **kwargs) -> Dict[str, Any]:
        """Read file contents."""
        path = kwargs.get("path")
        encoding = kwargs.get("encoding", "utf-8")
        start_line = kwargs.get("start_line", 0)
        end_line = kwargs.get("end_line", None)

        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"File does not exist: {path}",
                    "logs": [f"Path not found: {path}"],
                    "data": None
                }

            if not path_obj.is_file():
                return {
                    "success": False,
                    "reason": f"Path is not a file: {path}",
                    "logs": [f"Path is a directory, not file: {path}"],
                    "data": None
                }

            with open(path_obj, 'r', encoding=encoding) as f:
                lines = f.readlines()

            # Handle line slicing
            if end_line is not None:
                selected_lines = lines[start_line:end_line]
            else:
                selected_lines = lines[start_line:]

            content = ''.join(selected_lines)
            return {
                "success": True,
                "reason": f"File read successfully: {path}",
                "logs": [f"Read {len(selected_lines)} lines from {path}"],
                "data": {
                    "path": str(path_obj.resolve()),
                    "content": content,
                    "lines_read": len(selected_lines),
                    "total_lines": len(lines),
                    "encoding": encoding
                }
            }
        except UnicodeDecodeError:
            return {
                "success": False,
                "reason": f"Encoding error reading file: {path}",
                "logs": [f"Cannot decode file with {encoding} encoding"],
                "data": {"path": path}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to read file: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _write_file(self, **kwargs) -> Dict[str, Any]:
        """Write file contents."""
        path = kwargs.get("path")
        content = kwargs.get("content", "")
        encoding = kwargs.get("encoding", "utf-8")
        append = kwargs.get("append", False)

        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            # Create parent directories if needed
            path_obj.parent.mkdir(parents=True, exist_ok=True)

            mode = 'a' if append else 'w'
            with open(path_obj, mode, encoding=encoding) as f:
                f.write(content)

            return {
                "success": True,
                "reason": f"File written successfully: {path}",
                "logs": [f"Written to {path} ({'append' if append else 'write'} mode)"],
                "data": {
                    "path": str(path_obj.resolve()),
                    "bytes_written": len(content.encode(encoding)),
                    "encoding": encoding,
                    "mode": mode
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to write file: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _delete_file(self, **kwargs) -> Dict[str, Any]:
        """Delete a file."""
        path = kwargs.get("path")
        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"File does not exist: {path}",
                    "logs": [f"Path not found: {path}"],
                    "data": None
                }

            if not path_obj.is_file():
                return {
                    "success": False,
                    "reason": f"Path is not a file: {path}",
                    "logs": [f"Path is a directory, not file: {path}"],
                    "data": None
                }

            path_obj.unlink()
            return {
                "success": True,
                "reason": f"File deleted: {path}",
                "logs": [f"Deleted file: {path}"],
                "data": {"path": str(path_obj.resolve())}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to delete file: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _copy_file(self, **kwargs) -> Dict[str, Any]:
        """Copy a file."""
        src = kwargs.get("src")
        dst = kwargs.get("dst")

        if not src or not dst:
            return {
                "success": False,
                "reason": "src and dst parameters required",
                "logs": ["Please provide src and dst parameters"],
                "data": None
            }

        try:
            src_obj = Path(src)
            dst_obj = Path(dst)

            if not src_obj.exists():
                return {
                    "success": False,
                    "reason": f"Source file does not exist: {src}",
                    "logs": [f"Source not found: {src}"],
                    "data": None
                }

            if not src_obj.is_file():
                return {
                    "success": False,
                    "reason": f"Source is not a file: {src}",
                    "logs": [f"Source is a directory, not file: {src}"],
                    "data": None
                }

            # Create parent directories if needed
            dst_obj.parent.mkdir(parents=True, exist_ok=True)

            import shutil
            shutil.copy2(src_obj, dst_obj)

            return {
                "success": True,
                "reason": f"File copied: {src} -> {dst}",
                "logs": [f"Copied {src} to {dst}"],
                "data": {
                    "src": str(src_obj.resolve()),
                    "dst": str(dst_obj.resolve()),
                    "size": src_obj.stat().st_size
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to copy file: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"src": src, "dst": dst}
            }

    def _move_file(self, **kwargs) -> Dict[str, Any]:
        """Move a file."""
        src = kwargs.get("src")
        dst = kwargs.get("dst")

        if not src or not dst:
            return {
                "success": False,
                "reason": "src and dst parameters required",
                "logs": ["Please provide src and dst parameters"],
                "data": None
            }

        try:
            src_obj = Path(src)
            dst_obj = Path(dst)

            if not src_obj.exists():
                return {
                    "success": False,
                    "reason": f"Source file does not exist: {src}",
                    "logs": [f"Source not found: {src}"],
                    "data": None
                }

            if not src_obj.is_file():
                return {
                    "success": False,
                    "reason": f"Source is not a file: {src}",
                    "logs": [f"Source is a directory, not file: {src}"],
                    "data": None
                }

            # Create parent directories if needed
            dst_obj.parent.mkdir(parents=True, exist_ok=True)

            import shutil
            shutil.move(str(src_obj), str(dst_obj))

            return {
                "success": True,
                "reason": f"File moved: {src} -> {dst}",
                "logs": [f"Moved {src} to {dst}"],
                "data": {
                    "src": str(src_obj.resolve()),
                    "dst": str(dst_obj.resolve())
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to move file: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"src": src, "dst": dst}
            }

    def _resolve_path(self, **kwargs) -> Dict[str, Any]:
        """Resolve a path to absolute form."""
        path = kwargs.get("path")
        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            path_obj = Path(path).resolve()
            return {
                "success": True,
                "reason": f"Path resolved: {path} -> {path_obj}",
                "logs": [f"Resolved {path} to absolute path"],
                "data": {
                    "original": path,
                    "resolved": str(path_obj),
                    "is_absolute": path_obj.is_absolute()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to resolve path: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _search_files(self, **kwargs) -> Dict[str, Any]:
        """Search for files by pattern."""
        path = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "*")
        recursive = kwargs.get("recursive", True)
        file_only = kwargs.get("file_only", False)
        dir_only = kwargs.get("dir_only", False)

        if file_only and dir_only:
            return {
                "success": False,
                "reason": "Cannot specify both file_only and dir_only",
                "logs": ["Please specify either file_only or dir_only, not both"],
                "data": None
            }

        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"Search path does not exist: {path}",
                    "logs": [f"Path not found: {path}"],
                    "data": None
                }

            if not path_obj.is_dir():
                return {
                    "success": False,
                    "reason": f"Search path is not a directory: {path}",
                    "logs": [f"Path is a file, not directory: {path}"],
                    "data": None
                }

            # Search for files
            if recursive:
                iterator = path_obj.rglob(pattern)
            else:
                iterator = path_obj.glob(pattern)

            results = []
            for item in iterator:
                if file_only and not item.is_file():
                    continue
                if dir_only and not item.is_dir():
                    continue
                results.append(str(item))

            return {
                "success": True,
                "reason": f"Found {len(results)} items matching '{pattern}' in {path}",
                "logs": [f"Search completed: {pattern} in {path}", f"Found {len(results)} matches"],
                "data": {
                    "path": str(path_obj.resolve()),
                    "pattern": pattern,
                    "recursive": recursive,
                    "file_only": file_only,
                    "dir_only": dir_only,
                    "matches": results,
                    "count": len(results)
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to search files: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path, "pattern": pattern}
            }