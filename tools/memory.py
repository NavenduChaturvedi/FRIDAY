"""FRIDAY's long-term memory — facts about the user that persist across sessions.

The most relevant facts are already in her system prompt every turn; this tool
is for *changing* what she remembers, and for pulling up something specific
that isn't in the prompt right now.

Not the same as `notes` — that's a transient to-do list. This is durable
context: who the user is, what they're working on, what they prefer.
"""

from __future__ import annotations

from friday.config import Config
from friday.memory import CATEGORIES, MemoryStore

TOOL = {
    "name": "memory",
    "description": (
        "Manage what you remember about the user long-term. "
        "action='remember' with fact (and optional category) when they tell "
        "you something worth keeping — their name, job, preferences, projects, "
        "people in their life. action='recall' with a query to look up "
        "something specific. action='forget' with a query to delete matching "
        "facts. action='list' to review everything. Don't remember passwords, "
        "card numbers, or anything sensitive."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["remember", "recall", "forget", "list"],
            },
            "fact": {
                "type": "string",
                "description": "for 'remember': the thing to store, as a short statement",
            },
            "category": {
                "type": "string",
                "enum": list(CATEGORIES),
                "description": "for 'remember': which bucket (default 'misc')",
            },
            "query": {
                "type": "string",
                "description": "for 'recall' / 'forget': what to search for",
            },
        },
        "required": ["action"],
    },
}

_STORE = MemoryStore(Config().memory_path)


def run(action: str = "list", fact: str = "", category: str = "misc", query: str = "") -> str:
    action = (action or "list").strip().lower()

    if action == "remember":
        fact = (fact or "").strip()
        if not fact:
            return "What should I remember?"
        cat = _STORE.add(fact, category)
        if not cat:
            return "That was empty — nothing stored."
        return f"Got it — I'll remember that ({cat})."

    if action == "recall":
        hits = _STORE.search(query, limit=8)
        if not hits:
            return f"I don't have anything on {query!r}." if query else "My memory's empty."
        return "Here's what I have:\n" + "\n".join(h.line() for h in hits)

    if action == "forget":
        removed = _STORE.forget(query)
        if not removed:
            return f"Nothing matched {query!r}, so nothing to forget."
        if len(removed) == 1:
            return f"Forgotten: {removed[0]}"
        return f"Forgotten {len(removed)} things: " + "; ".join(removed)

    if action == "list":
        entries = _STORE.all_entries()
        if not entries:
            return "I haven't been told to remember anything yet."
        return "Everything I remember:\n" + "\n".join(e.line() for e in entries)

    return "I can remember, recall, forget, or list."
