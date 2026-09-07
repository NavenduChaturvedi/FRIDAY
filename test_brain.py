"""Brain smoke test: exercise the Gemini -> Ollama chain from the keyboard.

    python test_brain.py

No mic, no speakers. Type at FRIDAY, see which provider answered and how
long it took. Ctrl+C or an empty line to quit.
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

cfg = Config()
print(cfg.summary())
brain = Brain(cfg)
print("\nType a message (empty to quit).\n")

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
    print(f"friday > {reply}")
    print(f"        [{time.monotonic() - started:.1f}s | spoken: {clean_text_for_speech(reply)!r}]\n")
