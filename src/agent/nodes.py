from typing import Any

from langchain_core.messages import AIMessage

from src.agent.core.logger import get_logger
from src.agent.state import AgentState

logger = get_logger("nodes")


async def guardrail_input_node(state: AgentState, rails: Any = None) -> dict[str, Any]:
    """Front-door input checks for destructive commands, jailbreaks, and SSRF attempts."""
    last_msg = state["messages"][-1]
    user_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    logger.info(f"Checking input safety | length={len(user_text)}")
    lower = user_text.lower()
    is_blocked = False
    refusal_reason = ""

    if any(w in lower for w in ["delete files", "rm -rf", "wipe", "format c:", "format disk"]):
        is_blocked = True
        refusal_reason = (
            "I cannot execute destructive filesystem commands or access protected directories."
        )
    elif any(
        w in lower
        for w in [
            "ignore all previous instructions",
            "disregard your system prompt",
            "you are now dan mode",
        ]
    ):
        is_blocked = True
        refusal_reason = (
            "I cannot comply with requests that attempt to bypass system safety constraints."
        )
    elif any(
        w in lower for w in ["127.0.0.1", "localhost", "10.", "192.168.", "172.16.", "169.254."]
    ) and any(w in lower for w in ["scrape", "read", "fetch", "http://", "https://"]):
        is_blocked = True
        refusal_reason = "I am not permitted to access internal network addresses."
    elif any(w in lower for w in ["os.remove", "shutil.rmtree", "rmdir /s"]) and any(
        w in lower for w in ["run", "execute", "python", "script"]
    ):
        is_blocked = True
        refusal_reason = "I cannot execute destructive filesystem operations or directory traversals. Please rewrite your code to only create and modify files within the 'scratch/ephemeral/' path."

    if is_blocked:
        logger.warning(f"Input blocked: query={user_text!r} | reason={refusal_reason}")
        return {
            "guardrail_response": refusal_reason,
            "is_blocked": True,
            "messages": [AIMessage(content=refusal_reason)],
        }

    return {"is_blocked": False}


async def agent_node(state: AgentState, bound_model: Any) -> dict[str, Any]:
    """Main model node invoking the tool-bound LLM."""
    messages = state["messages"]
    logger.info(f"Agent turn | message_count={len(messages)}")

    response = await bound_model.ainvoke(messages)

    if response.tool_calls:
        names = [tc.get("name") for tc in response.tool_calls]
        logger.info(f"Tool calls requested: {names}")
    else:
        logger.info(
            f"Final response produced | length={len(response.content) if response.content else 0}"
        )

    return {"messages": [response]}


async def guardrail_output_node(state: AgentState, rails: Any = None) -> dict[str, Any]:
    """Inspects final assistant message before returning."""
    last_msg = state["messages"][-1]
    output_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    return {
        "guardrail_response": output_text,
        "is_blocked": False,
    }
