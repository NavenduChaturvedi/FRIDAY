"""Recent headlines, via DuckDuckGo News."""

from __future__ import annotations

TOOL = {
    "name": "get_news",
    "description": (
        "Recent news headlines, optionally about a topic. Use for 'what's in "
        "the news', 'any news about the election', 'latest on SpaceX'. Returns "
        "a handful of headlines — read out two or three, don't list them all."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Optional subject; omit for general top news.",
            },
        },
        "required": [],
    },
}

_MAX = 5


def run(topic: str = "") -> str:
    topic = (topic or "").strip()
    try:
        from ddgs import DDGS
    except ImportError:
        return "News isn't available — the ddgs package isn't installed."

    query = topic or "today's top news"
    try:
        with DDGS() as ddg:
            items = ddg.news(query, max_results=_MAX)
    except Exception as exc:  # noqa: BLE001
        return f"The news lookup failed: {exc}"

    if not items:
        return f"No news found for {topic!r}." if topic else "No news found."

    lines = []
    for it in items:
        title = (it.get("title") or "").strip()
        source = (it.get("source") or "").strip()
        if title:
            lines.append(f"- {title}" + (f" ({source})" if source else ""))
    header = f"Headlines on {topic}:" if topic else "Top headlines:"
    return header + "\n" + "\n".join(lines)
