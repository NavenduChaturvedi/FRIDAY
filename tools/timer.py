"""Countdown timers. FRIDAY says something when one goes off."""

from __future__ import annotations

import threading

TOOL = {
    "name": "set_timer",
    "description": (
        "Start a countdown timer. When it finishes, FRIDAY announces it out "
        "loud on the next turn. Use for 'remind me in 10 minutes', 'set a "
        "5 minute timer', 'ping me in an hour'. Give the duration in seconds."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "seconds": {
                "type": "integer",
                "description": "How long until the timer fires, in seconds.",
            },
            "label": {
                "type": "string",
                "description": "Optional name, e.g. 'tea', 'stretch break'.",
            },
        },
        "required": ["seconds"],
    },
}

_MAX_SECONDS = 24 * 60 * 60  # a day; timers don't survive a restart anyway
_active: list[threading.Timer] = []


def _spoken_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    if seconds < 3600:
        m = round(seconds / 60)
        return f"{m} minute{'s' if m != 1 else ''}"
    h = seconds / 3600
    return f"{h:.1f}".rstrip("0").rstrip(".") + f" hour{'s' if h != 1 else ''}"


def run(seconds: int = 0, label: str = "", notify=None) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "I need the timer length as a number of seconds."
    if seconds <= 0:
        return "That timer needs to be longer than zero seconds."
    if seconds > _MAX_SECONDS:
        return "I can't set a timer longer than a day."

    label = (label or "").strip()
    dur = _spoken_duration(seconds)

    def fire() -> None:
        if notify:
            msg = f"That's your {label} timer." if label else f"Your {dur} timer is up."
            notify(msg)

    t = threading.Timer(seconds, fire)
    t.daemon = True
    t.start()
    _active.append(t)

    return (
        f"{label.capitalize()} timer set for {dur}."
        if label
        else f"Timer set for {dur}."
    )
