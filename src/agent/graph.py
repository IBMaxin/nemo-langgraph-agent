import os
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from nemoguardrails import LLMRails, RailsConfig

from src.agent.core.logger import get_logger
from src.agent.nodes import agent_node, guardrail_input_node, guardrail_output_node
from src.agent.state import AgentState
from src.agent.tools import ALL_TOOLS

logger = get_logger("graph")

DEFAULT_CHECKPOINT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "checkpoints.db"


def get_async_checkpointer(db_path: str | None = None) -> AsyncSqliteSaver:
    """Creates an async SQLite checkpointer for thread persistence."""
    path = db_path or str(DEFAULT_CHECKPOINT_DB)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return AsyncSqliteSaver.from_conn_string(path)


def build_guardrailed_graph(
    config_path: str = "config/rails",
    checkpointer: Any | None = None,
    interrupt_tools: bool = True,
):
    """Builds and compiles the LangGraph ReAct workflow."""
    logger.info(f"Loading NeMo config from '{config_path}'...")
    rails_config = RailsConfig.from_path(config_path)

    model_name = os.getenv("LOCAL_MODEL_NAME")
    if not model_name and rails_config.models:
        model_name = rails_config.models[0].model
    elif model_name and rails_config.models:
        rails_config.models[0].model = model_name

    base_url = os.getenv("LOCAL_OPENAI_BASE_URL")
    if not base_url and rails_config.models and rails_config.models[0].parameters:
        base_url = rails_config.models[0].parameters.get("base_url", "http://127.0.0.1:1234/v1")
    elif base_url and rails_config.models and rails_config.models[0].parameters:
        rails_config.models[0].parameters["base_url"] = base_url

    api_key = os.getenv("LOCAL_OPENAI_API_KEY", "lmstudio")
    temperature = float(os.getenv("AGENT_TEMPERATURE", "0.2"))

    rails = LLMRails(rails_config)

    bound_model = ChatOpenAI(
        model=model_name or "nvidia-nemotron-3.5-bolt-e4b-4gb",
        base_url=base_url or "http://127.0.0.1:1234/v1",
        api_key=api_key,
        temperature=temperature,
    ).bind_tools(ALL_TOOLS)

    async def input_step(state: AgentState) -> dict[str, Any]:
        return await guardrail_input_node(state, rails)

    async def model_step(state: AgentState) -> dict[str, Any]:
        return await agent_node(state, bound_model)

    async def output_step(state: AgentState) -> dict[str, Any]:
        return await guardrail_output_node(state, rails)

    builder = StateGraph(AgentState)
    builder.add_node("guardrail_input", input_step)
    builder.add_node("agent", model_step)
    builder.add_node("tools", ToolNode(ALL_TOOLS))
    builder.add_node("guardrail_output", output_step)

    builder.add_edge(START, "guardrail_input")
    builder.add_conditional_edges(
        "guardrail_input",
        lambda s: "END" if s.get("is_blocked") else "agent",
        {"END": END, "agent": "agent"},
    )
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", "__end__": "guardrail_output"},
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("guardrail_output", END)

    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
        if interrupt_tools:
            compile_kwargs["interrupt_before"] = ["tools"]

    compiled = builder.compile(**compile_kwargs)
    return compiled
