"""Current date and time, in the local zone or any named timezone."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TOOL = {
    "name": "get_time",
    "description": (
        "The current date and time. Pass an IANA timezone name (e.g. "
        "'Asia/Tokyo', 'America/New_York', 'Europe/London') for time elsewhere; "
        "omit it for the user's local time. Use this instead of guessing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone name, or empty for local time.",
            },
        },
        "required": [],
    },
}

_ALIASES = {
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "london": "Europe/London",
    "uk": "Europe/London",
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "india": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "utc": "UTC",
    "gmt": "UTC",
}


def _clock(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.minute:02d} {ampm}"


def run(timezone: str = "") -> str:
    tz_name = (timezone or "").strip()

    if not tz_name:
        now = datetime.now().astimezone()
        return f"It's {_clock(now)} on {now.strftime('%A, %B')} {now.day}."

    key = _ALIASES.get(tz_name.lower(), tz_name)
    try:
        now = datetime.now(ZoneInfo(key))
    except (ZoneInfoNotFoundError, ValueError):
        return (
            f"I don't recognise the timezone {tz_name!r}. Try an IANA name like "
            "'Asia/Tokyo'."
        )
    label = key.split("/")[-1].replace("_", " ")
    return f"It's {_clock(now)} on {now.strftime('%A')} in {label}."
