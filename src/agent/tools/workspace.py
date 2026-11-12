from pathlib import Path
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


def _build_tree(
    dir_path: Path, prefix: str = "", current_depth: int = 0, max_depth: int = 2
) -> list[str]:
    if current_depth > max_depth:
        return []

    lines = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except (PermissionError, Exception) as e:
        return [f"{prefix}└── [Cannot access: {e}]"]

    filtered = [e for e in entries if e.name not in IGNORE_DIRS]
    total = len(filtered)

    for index, entry in enumerate(filtered):
        is_last = index == (total - 1)
        connector = "└── " if is_last else "├── "
        child_prefix = "    " if is_last else "│   "

        if entry.is_dir():
            lines.append(f"{prefix}{connector}{entry.name}/")
            if current_depth < max_depth:
                lines.extend(
                    _build_tree(entry, prefix + child_prefix, current_depth + 1, max_depth)
                )
        else:
            lines.append(f"{prefix}{connector}{entry.name}")

    return lines


@guardrailed_action(name="list_directory")
async def list_directory(directory_path: str = ".", max_depth: int = 2) -> dict[str, Any]:
    """Lists workspace files and folders in an indented tree view, skipping .venv and .git."""
    path_obj = Path(directory_path)

    if not is_path_safe(str(path_obj)):
        return {
            "success": False,
            "error": f"Access denied: '{directory_path}' is protected.",
        }

    if not path_obj.exists():
        return {"success": False, "error": f"Directory not found: '{directory_path}'"}

    if not path_obj.is_dir():
        return {
            "success": False,
            "error": f"Path is not a directory: '{directory_path}'",
        }

    tree_lines = [f"{path_obj.resolve().name}/"]
    tree_lines.extend(_build_tree(path_obj, max_depth=max_depth))

    return {
        "success": True,
        "directory": str(path_obj),
        "tree": "\n".join(tree_lines),
    }
