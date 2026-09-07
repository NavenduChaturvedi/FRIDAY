"""Web search via DuckDuckGo. Returns a few snippets for the model to summarise."""

from __future__ import annotations

TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for current information — news, facts, prices, "
        "anything that might have changed or that you're not sure about. "
        "Returns short snippets; summarise them for the user in a sentence or "
        "two and don't read out URLs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
        },
        "required": ["query"],
    },
}

_MAX_RESULTS = 4


def run(query: str = "") -> str:
    query = (query or "").strip()
    if not query:
        return "I need something to search for."

    try:
        from ddgs import DDGS
    except ImportError:
        return "Web search isn't available — the ddgs package isn't installed."

    try:
        with DDGS() as ddg:
            hits = ddg.text(query, max_results=_MAX_RESULTS)
    except Exception as exc:  # noqa: BLE001 — network, rate limit, parse errors
        return f"The search failed: {exc}"

    if not hits:
        return f"No results for {query!r}."

    lines = []
    for h in hits:
        title = (h.get("title") or "").strip()
        body = " ".join((h.get("body") or "").split())
        if body:
            lines.append(f"- {title}: {body}")
    return "Search results:\n" + "\n".join(lines)
