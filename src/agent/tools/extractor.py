from typing import Any

import trafilatura

from src.agent.core.decorators import guardrailed_action
from src.agent.core.security import is_url_safe


@guardrailed_action(name="read_web_article")
async def read_web_article(url: str, max_chars: int = 5000) -> dict[str, Any]:
    """Extracts clean text content from a web page URL using Trafilatura, stripping ads and HTML tags."""
    if not url or not url.strip().startswith(("http://", "https://")):
        return {
            "success": False,
            "error": f"Invalid URL '{url}'. Must start with http:// or https://",
        }

    safe, reason = is_url_safe(url.strip())
    if not safe:
        return {"success": False, "error": reason}

    try:
        downloaded = trafilatura.fetch_url(url.strip())
        if not downloaded:
            return {
                "success": False,
                "error": f"Could not download webpage from '{url}'.",
            }

        text = trafilatura.extract(
            downloaded,
            include_links=True,
            include_formatting=True,
            output_format="markdown",
        )

        if not text:
            text = trafilatura.extract(downloaded)

        if not text:
            return {
                "success": False,
                "error": f"No readable text could be extracted from '{url}'.",
            }

        metadata = trafilatura.extract_metadata(downloaded)
        title = metadata.title if metadata and metadata.title else "Untitled"

        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[... Truncated at {max_chars} chars ...]"
            truncated = True

        return {
            "success": True,
            "url": url,
            "title": title,
            "char_count": len(text),
            "is_truncated": truncated,
            "text": text,
        }
    except Exception as e:
        return {"success": False, "error": f"Extraction error: {e}"}
