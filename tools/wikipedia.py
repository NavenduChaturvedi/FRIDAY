"""Quick factual lookup — the lead paragraph of a Wikipedia article."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

TOOL = {
    "name": "wikipedia_lookup",
    "description": (
        "Look up a person, place, event, or concept and get a short factual "
        "summary from Wikipedia. Use for 'who is', 'what is', 'tell me about' "
        "questions about established facts. Not for current events or news — "
        "use web_search for those."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "What to look up, e.g. 'Ada Lovelace', 'CRISPR'.",
            },
        },
        "required": ["topic"],
    },
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "friday-assistant"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def run(topic: str = "") -> str:
    topic = (topic or "").strip()
    if not topic:
        return "Look up what?"

    try:
        # Resolve the best-matching title first, so 'einstein' finds the page.
        search = _get(
            "https://en.wikipedia.org/w/rest.php/v1/search/title?"
            + urllib.parse.urlencode({"q": topic, "limit": 1})
        )
        pages = search.get("pages") or []
        if not pages:
            return f"I found nothing on Wikipedia for {topic!r}."
        title = pages[0]["title"]

        summary = _get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(title.replace(" ", "_"))
        )
    except Exception as exc:  # noqa: BLE001
        return f"The Wikipedia lookup failed: {exc}"

    if summary.get("type") == "disambiguation":
        return f"{title!r} could mean several things — can you be more specific?"
    extract = (summary.get("extract") or "").strip()
    if not extract:
        return f"I found the {title!r} page but it had no summary."
    return extract
