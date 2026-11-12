import pytest

from src.agent.tools.memory import search_memory, store_memory
from src.agent.tools.workspace import list_directory


@pytest.mark.asyncio
async def test_list_directory():
    result = await list_directory.ainvoke({"directory_path": ".", "max_depth": 1})
    assert result["success"] is True
    assert "src/" in result["tree"] or "tests/" in result["tree"]


@pytest.mark.asyncio
async def test_memory_store_and_search():
    store_res = await store_memory.ainvoke(
        {
            "key": "test_fact",
            "content": "Python 3.13 was released with improvements.",
            "category": "testing",
        }
    )
    assert store_res["success"] is True

    search_res = await search_memory.ainvoke({"query": "Python 3.13", "limit": 5})
    assert search_res["success"] is True
    assert search_res["count"] >= 1
    assert any("Python 3.13" in item["content"] for item in search_res["results"])
