"""Copy this file, rename it (no leading underscore), fill in TOOL and run().

FRIDAY discovers it on the next launch — nothing else to wire up. Enable/disable
a tool by name with FRIDAY_TOOLS_ENABLED in .env.
"""

from __future__ import annotations

TOOL = {
    "name": "my_tool",  # snake_case, unique, <= 48 chars
    "description": (
        "One or two plain sentences the model uses to decide when to call this. "
        "Say what it does and, if it might be confused with another tool, which "
        "one to prefer instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "example": {"type": "string", "description": "what this argument is"},
        },
        "required": [],  # list the properties the model MUST supply
    },
}


def run(example: str = "") -> str:
    """Return a short, plain sentence — it goes straight to the model, and often
    on to the speaker. Don't raise; catch your own errors and return a sentence
    saying what went wrong (the loader will catch anything you miss anyway).

    A tool that needs to speak later (a timer, a reminder) can add ``notify`` to
    its signature: ``def run(seconds: int, notify=None)``. It receives a
    ``Callable[[str], None]``; whatever you pass it is spoken by the main loop
    at the start of the next turn.
    """
    return f"Did the thing with {example!r}."
