import asyncio
import datetime
from pathlib import Path
from typing import Any

from src.agent.core.decorators import guardrailed_action
from src.agent.core.security import is_code_safe

EPHEMERAL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scratch" / "ephemeral"


@guardrailed_action(name="execute_python_code")
async def execute_python_code(code: str) -> dict[str, Any]:
    """Runs a Python script in an isolated subprocess with 'uv run'. Supports inline PEP 723 dependencies."""
    if not code or not code.strip():
        return {"success": False, "error": "Code snippet is empty."}

    safe, reason = is_code_safe(code)
    if not safe:
        return {"success": False, "error": reason}

    EPHEMERAL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    script_path = EPHEMERAL_DIR / f"run_{stamp}.py"

    try:
        script_path.write_text(code, encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": f"Failed to write script: {e}"}

    try:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "--no-project",
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(EPHEMERAL_DIR),
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "success": False,
                "error": "Execution timed out (10s limit exceeded).",
                "script_path": str(script_path),
            }

        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": stdout_b.decode("utf-8", errors="replace").strip(),
            "stderr": stderr_b.decode("utf-8", errors="replace").strip(),
            "script_path": str(script_path),
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Process error: {e}",
            "script_path": str(script_path),
        }
