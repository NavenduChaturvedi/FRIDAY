"""Brain smoke test: exercise the routed provider chain (with tools) by keyboard.

    python test_brain.py

No mic, no speakers. Type at FRIDAY; each reply prints sentence by sentence as
the brain streams it, with a timestamp — so you can see how soon speech would
start. Ctrl+C or an empty line to quit.
"""

import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from friday.brain import Brain
from friday.config import Config
from friday.toolbox import Toolbox

cfg = Config()
print(cfg.summary())

toolbox = Toolbox(cfg.tools_path, cfg.tools_enabled)
print(f"tools: {', '.join(toolbox.names) or '(none)'}")
for skip in toolbox.skipped:
    print(f"  skipped — {skip}")

brain = Brain(cfg, toolbox)
print("\nType a message (empty to quit). Try: what time is it in Tokyo?\n")

while True:
    try:
        msg = input("you > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        break
    if not msg:
        break
    started = time.monotonic()
    first = None
    for sentence in brain.stream_reply(msg):
        now = time.monotonic() - started
        if first is None:
            first = now
        print(f"  [{now:5.1f}s] {sentence}")
    for note in toolbox.drain_notifications():
        print(f"  (timer queued: {note!r})")
    if first is not None:
        print(
            f"        [first sentence {first:.1f}s, "
            f"done {time.monotonic() - started:.1f}s]\n"
        )
