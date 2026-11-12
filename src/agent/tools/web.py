from typing import Any

from ddgs import DDGS

from src.agent.core.decorators import guardrailed_action


@guardrailed_action(name="ddg_web_search")
async def ddg_web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Searches DuckDuckGo for live facts, documentation, or news, returning top snippets and URLs."""
    if not query or not query.strip():
        return {"success": False, "error": "Search query cannot be empty."}

    try:
        results: list[dict[str, str]] = []
        with DDGS() as ddgs:
            raw_results = ddgs.text(query.strip(), max_results=max_results)
            for item in raw_results:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", ""),
                    }
                )

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        return {"success": False, "error": f"Search error: {e}"}
