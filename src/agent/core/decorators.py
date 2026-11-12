import functools
import time
from collections.abc import Callable
from typing import Any

from langchain_core.tools import tool as lc_tool
from nemoguardrails.actions import action as nemo_action

from src.agent.core.logger import get_logger

logger = get_logger("actions")


def guardrailed_action(name: str | None = None):
    """Decorator registering an action with both LangChain and NeMo, logging execution time and status."""

    def decorator(fn: Callable) -> Any:
        tool_name = name or fn.__name__

        @nemo_action(name=tool_name, is_system_action=True)
        @functools.wraps(fn)
        async def logging_wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            logger.info(f"START tool=[{tool_name}] | args={args} kwargs={kwargs}")
            try:
                result = await fn(*args, **kwargs)
                elapsed = time.perf_counter() - t0
                status = "SUCCESS"
                if isinstance(result, dict) and not result.get("success", True):
                    status = "BLOCKED"
                logger.info(f"{status} tool=[{tool_name}] in {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.perf_counter() - t0
                logger.exception(f"FAIL tool=[{tool_name}] in {elapsed:.3f}s: {e}")
                raise

        # Wrap with LangChain tool decorator for schema extraction
        return lc_tool(name_or_callable=tool_name)(logging_wrapper)

    return decorator
