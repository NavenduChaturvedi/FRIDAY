"""Coin flips, dice, random numbers, and picking from a list."""

from __future__ import annotations

import random

TOOL = {
    "name": "random_choice",
    "description": (
        "Make a random decision: flip a coin, roll dice, pick a number in a "
        "range, or choose one item from a list the user gives. Use for 'flip a "
        "coin', 'roll a d20', 'pick a number 1 to 100', 'should I have pizza "
        "or sushi'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["coin", "dice", "number", "pick"],
                "description": "coin | dice | number | pick",
            },
            "sides": {"type": "integer", "description": "dice: sides per die (default 6)"},
            "count": {"type": "integer", "description": "dice: how many dice (default 1)"},
            "low": {"type": "integer", "description": "number: minimum (default 1)"},
            "high": {"type": "integer", "description": "number: maximum (default 100)"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "pick: the choices to choose between",
            },
        },
        "required": ["kind"],
    },
}


def run(kind: str = "coin", sides: int = 6, count: int = 1,
        low: int = 1, high: int = 100, options=None) -> str:
    kind = (kind or "coin").strip().lower()

    if kind == "coin":
        return random.choice(("Heads.", "Tails."))

    if kind == "dice":
        sides = max(2, int(sides or 6))
        count = min(max(1, int(count or 1)), 20)
        rolls = [random.randint(1, sides) for _ in range(count)]
        if count == 1:
            return f"You rolled a {rolls[0]} on a d{sides}."
        return f"You rolled {rolls} — total {sum(rolls)}."

    if kind == "number":
        low, high = int(low), int(high)
        if low > high:
            low, high = high, low
        return f"{random.randint(low, high)}."

    if kind == "pick":
        opts = [str(o).strip() for o in (options or []) if str(o).strip()]
        if not opts:
            return "Give me some options to pick from."
        return f"{random.choice(opts)}."

    return "I can flip a coin, roll dice, pick a number, or choose from a list."
