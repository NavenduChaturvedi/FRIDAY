"""Confirmation gate + undo — no models, throwaway state dir.

    python test_confirm.py

Covers the Toolbox side (park a destructive call, run/drop it, snapshot &
undo) and the Brain-side interception (yes/no/undo phrases), with a stub
provider so no LLM is needed.
"""

import os
import tempfile
from pathlib import Path

_STATE = Path(tempfile.mkdtemp())
os.environ["FRIDAY_STATE_DIR"] = str(_STATE)
os.environ["FRIDAY_BRAIN_ORDER"] = "stub"  # keep real providers out of it

from friday.config import Config  # noqa: E402
from friday import brain as brain_mod  # noqa: E402
from friday.brain import Brain, Turn  # noqa: E402
from friday.toolbox import Toolbox  # noqa: E402

cfg = Config()
NOTES = _STATE / "notes.json"


def fresh_box(confirm=True):
    for f in _STATE.glob("*.json"):
        f.unlink()
    return Toolbox(cfg.tools_path, ["notes", "memory"], confirm=confirm)


# -- Toolbox: declaration parsing -----------------------------------------
box = fresh_box()
notes = box._tools["notes"]
assert notes.will_mutate({"action": "add"}) and notes.will_mutate({"action": "clear"})
assert not notes.will_mutate({"action": "list"})
assert notes.needs_confirm({"action": "clear"}) is True
assert notes.needs_confirm({"action": "add", "text": "x"}) is False
assert notes.needs_confirm({"action": "remove", "index": 1}) is False
print("ok  declaration: notes confirms on clear, mutates on writes not reads")

# -- a non-destructive call runs straight through, and is snapshotted -----
assert "1 thing" in box.call("notes", {"action": "add", "text": "milk"})
assert "2 things" in box.call("notes", {"action": "add", "text": "eggs"})
assert box.pending is None
print("ok  add: runs without confirmation")

# -- undo reverses the last add -----------------------------------------
assert "eggs" in box.call("notes", {"action": "list"})
msg = box.undo_last()
assert msg and "reversed" in msg, msg
listed = box.call("notes", {"action": "list"})
assert "milk" in listed and "eggs" not in listed, listed
assert box.undo_last() is None  # one level only
print("ok  undo: last add rolled back, single level")

# -- clear is parked, not executed ------------------------------------
box.call("notes", {"action": "add", "text": "eggs"})
out = box.call("notes", {"action": "clear"})
assert "CONFIRMATION REQUIRED" in out, out
assert box.pending is not None and box.pending.name == "notes"
assert "2 note" in box.pending.prompt, box.pending.prompt
assert "milk" in box.call("notes", {"action": "list"})  # still there
print("ok  clear: parked, notes untouched")

# -- resolve yes runs it, and it's undoable --------------------------
said = box.resolve_pending(True)
assert "cleared" in said.lower(), said
assert box.pending is None
assert "empty" in box.call("notes", {"action": "list"}).lower()
assert "reversed" in (box.undo_last() or "")
assert "milk" in box.call("notes", {"action": "list"})
print("ok  confirm yes: clear runs, then undo restores")

# -- resolve no drops it ------------------------------------------------
box.call("notes", {"action": "clear"})
assert box.pending is not None
dropped = box.resolve_pending(False)
assert "leave" in dropped.lower()
assert box.pending is None
assert "milk" in box.call("notes", {"action": "list"})
print("ok  confirm no: clear dropped")

# -- confirm=False bypasses the gate --------------------------------
nogate = fresh_box(confirm=False)
nogate.call("notes", {"action": "add", "text": "x"})
assert "cleared" in nogate.call("notes", {"action": "clear"}).lower()
assert nogate.pending is None
print("ok  confirm=False: gate disabled, clear runs immediately")


# -- Brain interception with a stub provider -------------------------
class StubProvider:
    name = "stub"

    def __init__(self, cfg):
        self.calls = []

    def stream(self, system, history, user_text, toolbox, route):
        # Model "decides" to clear the notes on any turn mentioning "wipe".
        if "wipe" in user_text.lower():
            result = toolbox.call("notes", {"action": "clear"})
            self.calls.append(result)
            yield "Okay."  # a weak reply with no question mark
        else:
            yield "Sure thing."


brain_mod._FACTORIES["stub"] = StubProvider
b = Brain(cfg, fresh_box())
b._toolbox.call("notes", {"action": "add", "text": "keep me"})

# turn 1: model clears -> parked, and Brain voices the ask (model didn't)
r1 = " ".join(b.stream_reply("wipe my list"))
assert b._toolbox.pending is not None, "should be parked"
assert "?" in r1 and "go ahead" in r1.lower(), r1
assert "keep me" in b._toolbox.call("notes", {"action": "list"})
print("ok  brain: parked call gets a spoken question even on a weak reply")

# turn 2: "yes" runs it
r2 = " ".join(b.stream_reply("yes"))
assert "cleared" in r2.lower(), r2
assert b._toolbox.pending is None
assert "empty" in b._toolbox.call("notes", {"action": "list"}).lower()
print("ok  brain: 'yes' executes the parked call")

# turn 3: "undo that" brings it back
r3 = " ".join(b.stream_reply("undo that"))
assert "reversed" in r3.lower(), r3
assert "keep me" in b._toolbox.call("notes", {"action": "list"})
print("ok  brain: 'undo that' restores")

# a parked call is dropped if the next turn is neither yes nor no
b._toolbox.call("notes", {"action": "clear"})
assert b._toolbox.pending is not None
r4 = " ".join(b.stream_reply("what's the weather"))
assert b._toolbox.pending is None, "unrelated turn should drop the parked call"
assert "keep me" in b._toolbox.call("notes", {"action": "list"})
print("ok  brain: unrelated turn drops the parked call")

# "no" acknowledges and drops
b._toolbox.call("notes", {"action": "clear"})
r5 = " ".join(b.stream_reply("no, don't"))
assert "leave" in r5.lower(), r5
assert b._toolbox.pending is None
print("ok  brain: 'no' drops the parked call")

# undo with nothing to undo
b2 = Brain(cfg, fresh_box())
assert "nothing" in " ".join(b2.stream_reply("undo")).lower()
print("ok  brain: undo with empty history is graceful")

print("\nall passed")
