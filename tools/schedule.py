"""Recurring scheduled announcements, and the morning briefing.

Unlike ``reminder`` (one-shot — "remind me at 3pm today"), a schedule *repeats*:
"every weekday at 7am". A job either speaks a line you gave it, or — for the
special task ``briefing`` — reads out the morning rundown: the time, the
weather for ``FRIDAY_HOME_CITY``, today's reminders, what's on your notes list,
and (with ``FRIDAY_BRIEFING_NEWS=true``) a couple of headlines.

Stored in ``state/schedule.json``, checked by a background thread started at
launch. Like a reminder, a due job is only *spoken on your next turn*.

The briefing is a plain template filled from the other tools — no LLM — so it
works even when the model is unloaded or offline.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta

from friday.config import Config

TOOL = {
    "name": "schedule",
    "description": (
        "Set up a REPEATING spoken announcement. action='add' with when (a "
        "clock time like '7am' or '18:30'), repeat ('daily', 'weekdays', "
        "'weekends', 'once'), and task — either a sentence to say, or the word "
        "'briefing' for the morning rundown (time, weather, reminders, notes). "
        "action='list' to hear what's scheduled; action='cancel' with index to "
        "drop one. For a single one-off reminder use the 'reminder' tool "
        "instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "cancel"]},
            "when": {
                "type": "string",
                "description": "for 'add': a clock time, e.g. '7am' or '18:30'",
            },
            "repeat": {
                "type": "string",
                "enum": ["daily", "weekdays", "weekends", "once"],
                "description": "for 'add': how often (default 'daily')",
            },
            "task": {
                "type": "string",
                "description": (
                    "for 'add': a line to speak, or 'briefing' for the morning "
                    "rundown. Default 'briefing'."
                ),
            },
            "index": {"type": "integer", "description": "for 'cancel': the job number"},
        },
        "required": ["action"],
    },
}

_PATH = Config().state_path / "schedule.json"
_lock = threading.Lock()
_notify = None      # set by on_load()
_toolbox = None     # set by on_load() — used to fetch weather/news for a briefing

_REPEATS = ("daily", "weekdays", "weekends", "once")


# -- storage ----------------------------------------------------------------
def _load() -> list[dict]:
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _save(items: list[dict]) -> None:
    _PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


# -- helpers --------------------------------------------------------------
def _clock(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _parse_when(when: str) -> datetime | None:
    try:
        import dateparser
    except ImportError:
        return None
    return dateparser.parse(
        when,
        settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False},
    )


def _repeat_matches(repeat: str, weekday: int) -> bool:
    if repeat == "daily":
        return True
    if repeat == "weekdays":
        return weekday < 5
    if repeat == "weekends":
        return weekday >= 5
    return False  # 'once' is matched by date, not weekday


def _task_label(job: dict) -> str:
    task = job.get("task", "")
    return "the morning briefing" if task == "briefing" else f'"{task}"'


def _describe(job: dict) -> str:
    try:
        when = _clock(datetime.strptime(job["time"], "%H:%M"))
    except (KeyError, ValueError):
        when = job.get("time", "?")
    if job.get("repeat") == "once":
        return f"{_task_label(job)} on {job.get('date', '?')} at {when}"
    return f"{_task_label(job)}, {job.get('repeat', 'daily')}, at {when}"


# -- the tool -----------------------------------------------------------
def run(
    action: str = "list",
    when: str = "",
    repeat: str = "",
    task: str = "",
    index: int = 0,
) -> str:
    action = (action or "list").strip().lower()

    if action == "add":
        dt = _parse_when((when or "").strip())
        if dt is None:
            return (
                f"I couldn't work out what time {when!r} is. Try '7am' or '18:30'."
                if when
                else "What time should I schedule it for?"
            )
        task = (task or "briefing").strip()
        repeat = (repeat or "").strip().lower()
        if repeat not in _REPEATS:
            repeat = "once" if dt.date() > datetime.now().date() else "daily"
        job = {
            "time": dt.strftime("%H:%M"),
            "repeat": repeat,
            "task": task,
            "last_run": "",
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        if repeat == "once":
            job["date"] = dt.strftime("%Y-%m-%d")
        with _lock:
            items = _load()
            items.append(job)
            _save(items)
        return f"Done — {_describe(job)}."

    with _lock:
        items = _load()

        if action == "list":
            if not items:
                return "Nothing's scheduled."
            lines = [f"{i}. {_describe(j)}" for i, j in enumerate(items, 1)]
            return "Scheduled:\n" + "\n".join(lines)

        if action == "cancel":
            try:
                i = int(index)
            except (TypeError, ValueError):
                return "Which one? Give me the number from the list."
            if not 1 <= i <= len(items):
                return f"There's no job {i} — you have {len(items)}."
            gone = items.pop(i - 1)
            _save(items)
            return f"Cancelled {_describe(gone)}."

    return "I can add, list, or cancel scheduled jobs."


# -- the background checker -------------------------------------------
def _due(job: dict, now: datetime, today: str, grace: int) -> str:
    """'fire' | 'skip' (mark done, don't speak) | 'expire' (drop) | 'no'."""
    if job.get("last_run") == today:
        return "no"
    if job.get("repeat") == "once":
        date = job.get("date", "")
        if date and date < today:
            return "expire"  # the day came and went while FRIDAY was off
        if date != today:
            return "no"
    elif not _repeat_matches(job.get("repeat", "daily"), now.weekday()):
        return "no"
    try:
        sched = datetime.strptime(f"{today} {job['time']}", "%Y-%m-%d %H:%M")
    except (KeyError, ValueError):
        return "no"
    if now < sched:
        return "no"
    if job.get("task") != "briefing" and now - sched > timedelta(minutes=grace):
        return "skip"
    return "fire"


def _tick() -> None:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    grace = Config().schedule_grace_minutes
    fired: list[dict] = []
    with _lock:
        items = _load()
        keep: list[dict] = []
        changed = False
        for job in items:
            verdict = _due(job, now, today, grace)
            if verdict == "expire":
                changed = True
                continue
            if verdict in ("fire", "skip"):
                job["last_run"] = today
                changed = True
                if verdict == "fire":
                    fired.append(job)
                if job.get("repeat") == "once":
                    continue  # done, drop it
            keep.append(job)
        if changed:
            _save(keep)

    for job in fired:
        msg = (
            _compose_briefing()
            if job.get("task") == "briefing"
            else job.get("task", "")
        )
        if msg and _notify:
            _notify(msg)


def _check_loop() -> None:
    while True:
        time.sleep(30)
        try:
            _tick()
        except Exception:  # noqa: BLE001 — never let the checker thread die
            pass


def on_load(notify, toolbox=None) -> None:
    global _notify, _toolbox
    _notify = notify
    _toolbox = toolbox
    threading.Thread(
        target=_check_loop, daemon=True, name="friday-schedule"
    ).start()


# -- the morning briefing --------------------------------------------
def _safe_call(name: str, args: dict) -> str:
    box = _toolbox
    if box is None or name not in set(box.names):
        return ""
    try:
        res = box.call(name, args)
    except Exception:  # noqa: BLE001
        return ""
    res = (res or "").strip()
    return "" if not res or res.startswith(("(", "CONFIRMATION")) else res


def _todays_reminders(now: datetime) -> str:
    try:
        items = json.loads(
            (Config().state_path / "reminders.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ValueError):
        return ""
    today = now.strftime("%Y-%m-%d")
    due: list[tuple[datetime, str]] = []
    for x in items:
        w = x.get("when", "")
        if w[:10] != today or w <= now.isoformat():
            continue
        try:
            due.append((datetime.fromisoformat(w), x.get("text", "")))
        except ValueError:
            continue
    if not due:
        return ""
    due.sort()
    if len(due) == 1:
        t, txt = due[0]
        return f"One reminder today: {txt}, at {_clock(t)}."
    return f"{len(due)} reminders today: " + "; ".join(
        f"{txt} at {_clock(t)}" for t, txt in due
    ) + "."


def _notes_line() -> str:
    try:
        items = json.loads(
            (Config().state_path / "notes.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ValueError):
        return ""
    if not items:
        return ""
    if len(items) <= 3:
        return "On your list: " + "; ".join(i.get("text", "") for i in items) + "."
    return f"You've got {len(items)} things on your notes list."


def _compose_briefing() -> str:
    cfg = Config()
    now = datetime.now()
    out = [f"Morning. It's {_clock(now)} on {now:%A}, {now.day} {now:%B}."]

    if cfg.home_city:
        wx = _safe_call("get_weather", {"city": cfg.home_city})
        # Only if it's an actual forecast — drop "I couldn't find a place…" etc.
        if wx and "degree" in wx.lower():
            out.append(wx if wx.endswith(".") else wx + ".")

    for line in (_todays_reminders(now), _notes_line()):
        if line:
            out.append(line)

    if cfg.briefing_news:
        news = _safe_call("get_news", {})
        heads = [
            re.sub(r"\s*\([^)]*\)\s*$", "", ln.lstrip("- ").strip()).rstrip(".")
            for ln in news.splitlines()[1:3]
            if ln.strip().startswith("-")
        ]
        if heads:
            out.append("In the news: " + "; ".join(heads) + ".")

    if len(out) == 1:
        out.append("Nothing on the calendar, and your list is clear.")
    return " ".join(out)
