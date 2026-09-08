"""Wake-word filter test — no mic, just the addressed()/strip() logic.

    python test_wake.py
"""

import os

os.environ.pop("PICOVOICE_ACCESS_KEY", None)  # force filter mode
os.environ["FRIDAY_WAKE_WORD"] = "friday"

from friday.config import Config
from friday.wake import Wake

w = Wake(Config())
assert w.mode == "filter", w.mode

ADDRESSED = [
    ("friday what is the weather", "what is the weather"),
    ("hey friday set a timer for ten minutes", "set a timer for ten minutes"),
    ("okay friday, remind me at six", "remind me at six"),
    ("what is the weather friday", "what is the weather friday"),
    ("friday", "friday"),
]
NOT_ADDRESSED = [
    "what time is it",
    "i am going to the shop on friday",
    "on friday i have a meeting remind me",
    "next friday is my birthday",
    "remind me every friday to water the plants",
    "tell me a long rambling story about my week and also friday somewhere",
]

fails = 0
for text, want_strip in ADDRESSED:
    got = w.addressed(text)
    stripped = w.strip(text)
    ok = got and stripped == want_strip
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {text!r} -> addressed={got}, strip={stripped!r}")

for text in NOT_ADDRESSED:
    got = w.addressed(text)
    fails += got
    print(f"  {'ok  ' if not got else 'FAIL'} {text!r} -> addressed={got}")

print("\n" + ("all passed" if not fails else f"{fails} failed"))
raise SystemExit(1 if fails else 0)
