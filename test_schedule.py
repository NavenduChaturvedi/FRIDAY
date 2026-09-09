"""Scheduler + morning briefing — no models, throwaway state dir.

    python test_schedule.py

Covers add/list/cancel, the due/skip/expire logic, and briefing composition
with a stub toolbox and seeded reminders/notes.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta

_STATE = tempfile.mkdtemp()
os.environ["FRIDAY_STATE_DIR"] = _STATE
os.environ["FRIDAY_HOME_CITY"] = "Cambridge"
os.environ["FRIDAY_SCHEDULE_GRACE_MINUTES"] = "120"

import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "friday_tool_schedule", Path("tools/schedule.py")
)
sched = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sched)

SCHEDULE = Path(_STATE) / "schedule.json"


def reset():
    for name in ("schedule.json", "reminders.json", "notes.json"):
        p = Path(_STATE) / name
        if p.exists():
            p.unlink()


# -- add / list / cancel ------------------------------------------------
reset()
out = sched.run("add", when="7am", repeat="weekdays", task="briefing")
assert "morning briefing" in out and "weekdays" in out, out
jobs = json.loads(SCHEDULE.read_text())
assert jobs[0]["time"] == "07:00" and jobs[0]["repeat"] == "weekdays"
print("ok  add: briefing at 07:00 weekdays")

out = sched.run("add", when="6pm", task="take the bins out", repeat="daily")
assert '"take the bins out"' in out, out
listed = sched.run("list")
assert "1." in listed and "2." in listed, listed
print("ok  list: two jobs")

out = sched.run("cancel", index=1)
assert "Cancelled" in out
assert len(json.loads(SCHEDULE.read_text())) == 1
assert sched.run("cancel", index=9).startswith("There's no job")
print("ok  cancel: by index, out-of-range handled")

# repeat inferred: an explicit future date -> once
reset()
sched.run("add", when="2035-01-01 09:00")
job = json.loads(SCHEDULE.read_text())[0]
assert job["repeat"] == "once" and job["date"] == "2035-01-01", job
print("ok  add: explicit future date infers repeat=once")


# -- due logic --------------------------------------------------------
def due(job, now):
    return sched._due(job, now, now.strftime("%Y-%m-%d"), 120)


mon_8am = datetime(2026, 9, 7, 8, 0)
sat_8am = datetime(2026, 9, 12, 8, 0)
assert mon_8am.weekday() == 0 and sat_8am.weekday() == 5  # sanity

daily = {"time": "07:00", "repeat": "daily", "task": "briefing", "last_run": ""}
assert due(daily, mon_8am) == "fire"
assert due(daily, datetime(2026, 9, 7, 6, 0)) == "no"           # before 7am
daily_ran = dict(daily, last_run="2026-09-07")
assert due(daily_ran, mon_8am) == "no"                          # already ran
print("ok  due: daily fires once past its time")

wd = {"time": "07:00", "repeat": "weekdays", "task": "briefing", "last_run": ""}
assert due(wd, mon_8am) == "fire"
assert due(wd, sat_8am) == "no"                                 # Saturday
print("ok  due: weekdays skips the weekend")

# a plain task more than grace minutes late is skipped, not fired
late = {"time": "07:00", "repeat": "daily", "task": "stretch", "last_run": ""}
assert due(late, datetime(2026, 9, 7, 10, 30)) == "skip"        # 3.5h late
assert due(late, datetime(2026, 9, 7, 8, 30)) == "fire"         # 1.5h late, ok
# the briefing always fires, however late
brief_late = dict(late, task="briefing")
assert due(brief_late, datetime(2026, 9, 7, 11, 0)) == "fire"
print("ok  due: stale plain task skipped, briefing always fires")

once_past = {"time": "07:00", "repeat": "once", "date": "2020-01-01", "task": "x", "last_run": ""}
assert due(once_past, mon_8am) == "expire"
print("ok  due: a 'once' job whose day passed expires")


# -- _tick fires and marks ------------------------------------------
reset()
fired = []
sched._notify = fired.append
sched._toolbox = None
_save = sched._save
past = (datetime.now() - timedelta(hours=1)).strftime("%H:%M")
sched._save([
    {"time": past, "repeat": "daily", "task": "drink water", "last_run": ""},
    {"time": past, "repeat": "once", "date": datetime.now().strftime("%Y-%m-%d"),
     "task": "one-shot", "last_run": ""},
])
sched._tick()
assert "drink water" in fired and "one-shot" in fired, fired
left = json.loads(SCHEDULE.read_text())
assert len(left) == 1 and left[0]["task"] == "drink water"      # once-job dropped
assert left[0]["last_run"] == datetime.now().strftime("%Y-%m-%d")
fired.clear()
sched._tick()
assert fired == []                                              # already ran today
print("ok  tick: fires due jobs, drops the 'once', won't re-fire same day")


# -- briefing composition -----------------------------------------
class StubBox:
    names = ["get_weather", "get_news"]

    def call(self, name, args):
        if name == "get_weather":
            assert args["city"] == "Cambridge"
            return "In Cambridge it's 12 degrees and overcast, today 8 to 14."
        if name == "get_news":
            return "Top headlines:\n- Budget passes\n- Rain expected\n- Team wins"
        return "(no such tool)"


reset()
now = datetime.now()
soon = (now + timedelta(hours=2)).replace(microsecond=0)
Path(_STATE, "reminders.json").write_text(json.dumps([
    {"when": soon.isoformat(), "text": "dentist"},
    {"when": (now - timedelta(hours=1)).isoformat(), "text": "past, skip me"},
]))
Path(_STATE, "notes.json").write_text(json.dumps([
    {"text": "buy milk"}, {"text": "email Sam"},
]))
sched._toolbox = StubBox()
b = sched._compose_briefing()
print("   briefing:", b)
assert b.startswith("Morning."), b
assert "Cambridge" in b and "12 degrees" in b
assert "dentist" in b and "past, skip me" not in b
assert "buy milk" in b and "email Sam" in b
assert "In the news" not in b                                   # FRIDAY_BRIEFING_NEWS unset
print("ok  briefing: time + weather + today's reminders + notes, no news")

os.environ["FRIDAY_BRIEFING_NEWS"] = "true"
b = sched._compose_briefing()
assert "In the news: Budget passes; Rain expected." in b, b
print("ok  briefing: news headlines when FRIDAY_BRIEFING_NEWS=true")

reset()
os.environ["FRIDAY_BRIEFING_NEWS"] = "false"
os.environ["FRIDAY_HOME_CITY"] = ""
sched._toolbox = StubBox()
b = sched._compose_briefing()
assert "Nothing on the calendar" in b, b
os.environ["FRIDAY_HOME_CITY"] = "Cambridge"
print("ok  briefing: empty day still reads cleanly")

print("\nall passed")
