"""Web search skill using DuckDuckGo (no API key required)."""

from duckduckgo_search import DDGS


def search(query: str, max_results: int = 5) -> str:
    """
    Search DuckDuckGo for *query* and return a plain-text summary of the
    top results suitable for Jarvis to speak aloud.
    """
    results = []
    with DDGS() as ddgs:
        for hit in ddgs.text(query, max_results=max_results):
            body = hit.get("body", "").strip()
            if body:
                results.append(body)
            if len(results) >= 3:
                break

    if not results:
        return "I couldn't find anything relevant."

    return " ".join(results)
