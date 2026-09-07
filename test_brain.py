"""Brain smoke test: exercise the Gemini -> Ollama chain (with tools) by keyboard.

    python test_brain.py

No mic, no speakers. Type at FRIDAY, see which provider answered, whether a
tool ran, and how long it took. Ctrl+C or an empty line to quit.
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
from friday.text import clean_text_for_speech
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
    reply = brain.ask(msg)
    for note in toolbox.drain_notifications():
        print(f"  (timer queued: {note!r})")
    print(f"friday > {reply}")
    print(
        f"        [{time.monotonic() - started:.1f}s | "
        f"spoken: {clean_text_for_speech(reply)!r}]\n"
    )
