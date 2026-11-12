import os
import re
from typing import Any

from src.agent.core.decorators import guardrailed_action
from src.agent.core.security import is_path_safe

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


@guardrailed_action(name="safe_read_file")
async def safe_read_file(path: str) -> dict[str, Any]:
    """Reads a file from the workspace, blocking access to system or protected paths."""
    if not is_path_safe(path):
        return {
            "success": False,
            "error": f"Access denied: '{path}' is a protected directory.",
        }

    if not os.path.exists(path):
        return {"success": False, "error": f"File not found: '{path}'"}

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {
            "success": True,
            "path": path,
            "content": content,
            "char_count": len(content),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@guardrailed_action(name="safe_search_codebase")
async def safe_search_codebase(pattern: str, base_dir: str = ".") -> dict[str, Any]:
    """Searches workspace files for a regex pattern, skipping virtual environments and cache directories."""
    if not is_path_safe(base_dir):
        return {
            "success": False,
            "error": f"Access denied: '{base_dir}' is a protected directory.",
        }

    matches = []
    regex = re.compile(pattern, re.IGNORECASE)

    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        if not is_path_safe(root):
            continue

        for file in files:
            if file.endswith((".py", ".yml", ".yaml", ".co", ".md", ".toml", ".json", ".txt")):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, encoding="utf-8", errors="ignore") as f:
                        for line_no, line in enumerate(f, start=1):
                            if regex.search(line):
                                matches.append(
                                    {
                                        "file": filepath,
                                        "line": line_no,
                                        "match": line.strip(),
                                    }
                                )
                except Exception:
                    continue

    return {"success": True, "count": len(matches), "matches": matches[:25]}
