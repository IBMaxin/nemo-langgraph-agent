"""AgentState schema for LangGraph."""

import operator
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Represents the multi-turn state of the LangGraph agent."""

    messages: Annotated[list[BaseMessage], operator.add]
    guardrail_response: str | None
    is_blocked: bool
    context: dict[str, Any]
