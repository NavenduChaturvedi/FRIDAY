"""A persistent scratchpad — jot things down, read them back, cross them off.

Survives restarts. Stored as JSON in the state directory (FRIDAY_STATE_DIR).
This is a simple flat list, not the categorised long-term memory that's
coming later — good for "remind me I left the car on level 3".
"""

from __future__ import annotations

import json
from datetime import datetime
from threading import Lock

from friday.config import Config

TOOL = {
    "name": "notes",
    "description": (
        "The user's scratchpad. action='add' to jot something down, 'list' to "
        "read it back, 'remove' to cross off item number N, 'clear' to wipe "
        "it. Use 'add' for 'note that...', 'remember I parked on level 3', "
        "'add milk to my list'. Use 'list' for 'what's on my list', 'read my "
        "notes'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "remove", "clear"],
            },
            "text": {"type": "string", "description": "for 'add': what to note"},
            "index": {"type": "integer", "description": "for 'remove': the item number"},
        },
        "required": ["action"],
    },
}

_PATH = Config().state_path / "notes.json"
_lock = Lock()


def _load() -> list[dict]:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    _PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def run(action: str = "list", text: str = "", index: int = 0) -> str:
    action = (action or "list").strip().lower()

    with _lock:
        items = _load()

        if action == "add":
            note = (text or "").strip()
            if not note:
                return "What should I note down?"
            items.append({"text": note, "added": datetime.now().strftime("%Y-%m-%d %H:%M")})
            _save(items)
            return f"Noted. That's {len(items)} thing{'s' if len(items) != 1 else ''} on your list."

        if action == "list":
            if not items:
                return "Your scratchpad is empty."
            lines = [f"{i}. {it['text']}" for i, it in enumerate(items, 1)]
            return "Your notes:\n" + "\n".join(lines)

        if action == "remove":
            try:
                i = int(index)
            except (TypeError, ValueError):
                return "Which item number should I remove?"
            if not 1 <= i <= len(items):
                return f"There's no item {i} — you have {len(items)}."
            gone = items.pop(i - 1)
            _save(items)
            return f"Crossed off: {gone['text']}."

        if action == "clear":
            _save([])
            return "Scratchpad cleared."

    return "I can add, list, remove, or clear notes."
