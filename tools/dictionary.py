"""Word definitions, from Wiktionary (Wikimedia REST API, no key)."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

TOOL = {
    "name": "define_word",
    "description": (
        "Define an English word — meaning and part of speech. Use for 'what "
        "does X mean', 'define X'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "word": {"type": "string", "description": "The word to define."},
        },
        "required": ["word"],
    },
}

_TAG = re.compile(r"<[^>]+>")


def _strip(s: str) -> str:
    return html.unescape(_TAG.sub("", s or "")).strip()


def run(word: str = "") -> str:
    word = (word or "").strip().lower()
    if not word:
        return "Define what?"

    url = "https://en.wiktionary.org/api/rest_v1/page/definition/" + urllib.parse.quote(word)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "friday-assistant"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return f"I don't have a definition for {word!r}."
        return f"The dictionary lookup failed: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"The dictionary lookup failed: {exc}"

    entries = data.get("en") or []
    if not entries:
        return f"I don't have an English definition for {word!r}."

    out: list[str] = []
    for entry in entries[:2]:
        pos = entry.get("partOfSpeech", "")
        defs = entry.get("definitions", [])
        if not defs:
            continue
        text = _strip(defs[0].get("definition", ""))
        if text:
            out.append(f"({pos}) {text}" if pos else text)
    if not out:
        return f"I found {word!r} but couldn't parse a definition."
    return f"{word}: " + " ".join(out)
