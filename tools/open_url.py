"""Open a web page in the default browser."""

from __future__ import annotations

import webbrowser

TOOL = {
    "name": "open_url",
    "description": (
        "Open a web page in the user's default browser. Use for 'open "
        "github.com', 'pull up the BBC', 'take me to my email'. Only for "
        "http/https pages. If the user names a well-known site without a URL, "
        "fill in the obvious one (e.g. 'youtube' -> https://youtube.com)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full http(s) URL to open."},
        },
        "required": ["url"],
    },
}


def run(url: str = "") -> str:
    url = (url or "").strip()
    if not url:
        return "Open which page?"
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if " " in url or "." not in url:
        return f"That doesn't look like a web address: {url!r}"

    try:
        opened = webbrowser.open(url)
    except Exception as exc:  # noqa: BLE001
        return f"I couldn't open the browser: {exc}"
    if not opened:
        return "I couldn't find a browser to open that in."
    return f"Opening {url}."
