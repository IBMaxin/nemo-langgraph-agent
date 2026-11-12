from src.agent.graph import build_guardrailed_graph


async def test_graph_compilation():
    graph = build_guardrailed_graph(
        config_path="config/rails", checkpointer=None, interrupt_tools=False
    )
    assert graph is not None
    # Verify graph node names
    assert "guardrail_input" in graph.nodes
    assert "agent" in graph.nodes
    assert "tools" in graph.nodes
    assert "guardrail_output" in graph.nodes
