"""friday_ui.py smoke test — no models, no mic.

    python test_ui.py

Exercises the Worker<->App queue protocol and, if a display is available,
builds the window, pumps a scripted event stream through it, and tears it
down. It does *not* start the real assistant.
"""

import queue

from friday_ui import App, Worker, _hint

# -- Worker: command handling is pure queue logic --------------------------
ui_q: queue.Queue = queue.Queue()
cmd_q: queue.Queue = queue.Queue()
w = Worker(ui_q, cmd_q)

assert w._interruptible() is False
cmd_q.put(("text", "what's the weather"))
assert w._interruptible() is True                      # a queued cmd pulls the recorder out
assert w._drain_cmds() == "what's the weather"
assert w._interruptible() is False

cmd_q.put(("mute", True))
cmd_q.put(("stop",))
cmd_q.put(("text", "hello"))
assert w._drain_cmds() == "hello"
assert w._muted is True and w._interrupt is True
print("ok  worker: text / mute / stop / quit drain correctly")

cmd_q.put(("quit",))
w._drain_cmds()
assert w._quit is True
print("ok  worker: quit sets the flag")

assert "type" in _hint(type("W", (), {"mode": "filter", "word": "friday"})())
print("ok  _hint reads the wake mode")

# -- App: build it, script an event stream, tear down -------------------
try:
    import tkinter as tk

    probe = tk.Tk()
    probe.destroy()
    have_display = True
except Exception as exc:  # noqa: BLE001
    have_display = False
    print(f"~~  no display ({exc}) — skipping the window smoke test")

if have_display:
    ui_q2: queue.Queue = queue.Queue()
    cmd_q2: queue.Queue = queue.Queue()
    app = App(ui_q2, cmd_q2)

    for ev in [
        ("notice", "brain=ollama  whisper=base"),
        ("threshold", 0.03),
        ("ready", "filter -> 'friday'  ·  say it or type"),
        ("state", "listening", None),
        ("level", 0.05),
        ("transcript", "you", "what time is it"),
        ("state", "thinking", None),
        ("state", "speaking", None),
        ("transcript", "friday", "It's just past nine."),
        ("transcript", "notice", "(not for me: hello there)"),
        ("transcript", "error", "brain error: everything's down"),
        ("state", "idle", "say 'friday, ...' or type"),
        ("level", 0.0),
    ]:
        ui_q2.put(ev)

    app._pump()                 # drain the scripted stream in one go
    app.update_idletasks()

    body = app._log.get("1.0", "end")
    assert "what time is it" in body and "just past nine" in body, body
    assert app._state_lbl["text"] == "Idle", app._state_lbl["text"]

    # the buttons and entry work without raising
    app._entry.insert(0, "hi friday")
    app._send()
    assert cmd_q2.get_nowait() == ("text", "hi friday")
    app._toggle_mute()
    assert cmd_q2.get_nowait() == ("mute", True)
    app._stop()
    assert cmd_q2.get_nowait() == ("stop",)

    ui_q2.put(("closed",))
    try:
        app._pump()              # processes "closed" -> destroy()
    except tk.TclError:
        pass                     # window already gone
    print("ok  window: builds, renders a scripted stream, buttons queue commands")

print("\nall passed")
