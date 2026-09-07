"""Time-based reminders that survive a restart and speak when they're due.

Unlike ``set_timer`` (in-process, gone on exit), these are written to
``state/reminders.json`` and checked by a background thread started at launch.
When one is due FRIDAY says it on her next turn.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime

from friday.config import Config

TOOL = {
    "name": "reminder",
    "description": (
        "Schedule a spoken reminder for a specific time. action='add' with "
        "when (e.g. 'in 20 minutes', 'tomorrow at 8am', '18:30') and text. "
        "action='list' to hear pending reminders, action='cancel' with index "
        "to drop one. Use this for anything with a clock time; use set_timer "
        "for a plain countdown."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "cancel"]},
            "when": {"type": "string", "description": "for 'add': natural time, e.g. 'in 1 hour'"},
            "text": {"type": "string", "description": "for 'add': what to remind about"},
            "index": {"type": "integer", "description": "for 'cancel': the reminder number"},
        },
        "required": ["action"],
    },
}

_PATH = Config().state_path / "reminders.json"
_lock = threading.Lock()
_notify = None  # set by on_load()


def _load() -> list[dict]:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    _PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _humanize(dt: datetime) -> str:
    now = datetime.now()
    delta = (dt - now).total_seconds()
    when_clock = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == now.date():
        return f"today at {when_clock}"
    if delta < 36 * 3600:
        return f"tomorrow at {when_clock}"
    return dt.strftime(f"%A the %d at {when_clock}")


def _parse(when: str) -> datetime | None:
    try:
        import dateparser
    except ImportError:
        return None
    return dateparser.parse(
        when, settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False}
    )


def _check_loop() -> None:
    while True:
        time.sleep(15)
        try:
            due_msgs = []
            with _lock:
                items = _load()
                now = datetime.now().isoformat()
                keep = [x for x in items if x["when"] > now]
                due_msgs = [x["text"] for x in items if x["when"] <= now]
                if due_msgs:
                    _save(keep)
            for msg in due_msgs:
                if _notify:
                    _notify(f"Reminder: {msg}")
        except Exception:  # noqa: BLE001 — never let the checker thread die
            pass


def on_load(notify) -> None:
    global _notify
    _notify = notify
    t = threading.Thread(target=_check_loop, daemon=True, name="friday-reminders")
    t.start()


def run(action: str = "list", when: str = "", text: str = "", index: int = 0) -> str:
    action = (action or "list").strip().lower()

    if action == "add":
        note = (text or "").strip()
        if not note:
            return "What should I remind you about?"
        dt = _parse((when or "").strip())
        if dt is None:
            return f"I couldn't work out when {when!r} is. Try 'in 30 minutes' or '7pm'."
        if dt <= datetime.now():
            return "That time's already passed."
        with _lock:
            items = _load()
            items.append({"when": dt.isoformat(), "text": note, "set": datetime.now().isoformat()})
            items.sort(key=lambda x: x["when"])
            _save(items)
        return f"I'll remind you {_humanize(dt)}: {note}."

    with _lock:
        items = _load()

    if action == "list":
        pending = [x for x in items if x["when"] > datetime.now().isoformat()]
        if not pending:
            return "No reminders set."
        lines = [
            f"{i}. {_humanize(datetime.fromisoformat(x['when']))} — {x['text']}"
            for i, x in enumerate(pending, 1)
        ]
        return "Reminders:\n" + "\n".join(lines)

    if action == "cancel":
        pending = [x for x in items if x["when"] > datetime.now().isoformat()]
        try:
            i = int(index)
        except (TypeError, ValueError):
            return "Which reminder number?"
        if not 1 <= i <= len(pending):
            return f"There's no reminder {i}."
        target = pending[i - 1]
        with _lock:
            remaining = [
                x for x in _load()
                if not (x["when"] == target["when"] and x["text"] == target["text"])
            ]
            _save(remaining)
        return f"Cancelled: {target['text']}."

    return "I can add, list, or cancel reminders."
