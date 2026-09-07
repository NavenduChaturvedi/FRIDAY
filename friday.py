"""F.R.I.D.A.Y. — a local, voice-driven assistant.

    python friday.py

Speak when you see "listening…"; pause to send. Say "goodbye Friday" (or
press Ctrl+C) to stop.

The pipeline, one turn at a time:

    mic → faster-whisper → Brain (Gemini → Ollama, with tools)
        → clean_text_for_speech → Piper → speakers

Everything is configured from the environment / ``.env`` — see
``friday/config.py`` and ``.env.example``. Tools live in ``tools/``.
"""

from __future__ import annotations

import sys


# Windows consoles often default to cp1252; the status lines below use emoji
# and the persona files use em-dashes. Force UTF-8 so a print() never crashes
# the loop.
def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8()

from friday.brain import Brain, BrainError
from friday.config import Config
from friday.text import clean_text_for_speech
from friday.toolbox import Toolbox
from friday.voice import Ears, Mouth


def run() -> int:
    cfg = Config()
    print("Waking F.R.I.D.A.Y. …")
    print(f"  {cfg.summary()}")

    toolbox = Toolbox(cfg.tools_path, cfg.tools_enabled)
    if toolbox.names:
        print(f"  tools: {', '.join(toolbox.names)}")
    for skip in toolbox.skipped:
        print(f"  tool skipped — {skip}", file=sys.stderr)

    ears = Ears(cfg)
    mouth = Mouth(cfg)
    brain = Brain(cfg, toolbox)

    print("\nOnline. Say 'goodbye Friday' to stop.\n")

    while True:
        # Anything a tool queued (a timer going off) gets spoken first.
        for note in toolbox.drain_notifications():
            print(f"🔔 {note}")
            mouth.say(clean_text_for_speech(note))

        user_text = ears.listen()
        if not user_text:
            continue

        print(f"👤 {user_text}")
        if any(phrase in user_text.lower() for phrase in cfg.exit_phrases):
            mouth.say("Powering down. Catch you later.")
            print("👋 done.")
            return 0

        try:
            reply = brain.ask(user_text)
        except BrainError as exc:
            print(f"⚠️  brain error: {exc}", file=sys.stderr)
            mouth.say("I lost my train of thought there. Say that again?")
            continue

        print(f"🤖 {reply}")
        mouth.say(clean_text_for_speech(reply))


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
