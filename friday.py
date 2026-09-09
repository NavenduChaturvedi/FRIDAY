"""F.R.I.D.A.Y. — a local, voice-driven assistant.

    python friday.py

Speak when you see "listening…"; pause to send. Say "goodbye Friday" (or
press Ctrl+C) to stop.

The pipeline, one turn at a time:

    wake word → mic → faster-whisper → Brain (routed Ollama/Gemini, with tools)
              → sentence by sentence → Piper → speakers

The brain streams its reply a sentence at a time and the mouth pipelines
synthesis with playback, so FRIDAY starts talking before she's finished
thinking. Everything is configured from the environment / ``.env`` — see
``friday/config.py`` and ``.env.example``. Tools live in ``tools/``.
"""

from __future__ import annotations

import sys
import threading


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
from friday.wake import Wake


def run() -> int:
    cfg = Config()
    print("Waking F.R.I.D.A.Y. …")
    print(f"  {cfg.summary()}")

    toolbox = Toolbox(cfg.tools_path, cfg.tools_enabled, confirm=cfg.confirm_actions)
    if toolbox.names:
        print(f"  tools: {', '.join(toolbox.names)}")
    for skip in toolbox.skipped:
        print(f"  tool skipped — {skip}", file=sys.stderr)

    ears = Ears(cfg)
    mouth = Mouth(cfg)
    wake = Wake(cfg)
    brain = Brain(cfg, toolbox)
    print(f"  wake: {wake.describe()}")

    if wake.mode == "porcupine":
        hint = f"Say '{wake.keyword}' to wake her."
    elif wake.mode == "filter":
        hint = f"Name her — '{wake.word}, …' — to get an answer."
    else:
        hint = "Responding to everything."
    print(f"\nOnline. {hint}\n")

    # Memory headroom: once the conversation has been quiet for a while, unload
    # the routed Ollama model so its ~5 GB is free while nobody's talking to
    # her. The next turn pays a cold load. A daemon Timer does the waiting; it's
    # cancelled the moment a real turn starts. 0 = off (rely on keep_alive).
    idle_unload = cfg.ollama_idle_unload
    idle_timer: threading.Timer | None = None

    def cancel_idle() -> None:
        nonlocal idle_timer
        if idle_timer is not None:
            idle_timer.cancel()
            idle_timer = None

    def arm_idle() -> None:
        nonlocal idle_timer
        if idle_unload <= 0:
            return
        cancel_idle()
        idle_timer = threading.Timer(idle_unload, brain.release)
        idle_timer.daemon = True
        idle_timer.start()

    try:
        while True:
            # Anything a tool queued (a timer going off) gets spoken first.
            for note in toolbox.drain_notifications():
                print(f"🔔 {note}")
                mouth.say(clean_text_for_speech(note))
            mouth.wait()

            wake.wait()  # blocks until the wake word in Porcupine mode; else instant
            heard = ears.listen()
            if not heard:
                continue

            cancel_idle()  # a real turn is starting — keep the model warm

            if any(phrase in heard.lower() for phrase in cfg.exit_phrases):
                mouth.say("Powering down. Catch you later.")
                mouth.wait()
                print("👋 done.")
                return 0

            if not wake.addressed(heard):
                print(f"   (not for me: {heard!r})")
                arm_idle()
                continue
            user_text = wake.strip(heard)

            print(f"👤 {user_text}")

            # Speak each sentence as the brain produces it.
            try:
                for sentence in brain.stream_reply(user_text):
                    print(f"🤖 {sentence}")
                    mouth.say(sentence)
            except BrainError as exc:
                print(f"⚠️  brain error: {exc}", file=sys.stderr)
                mouth.say("I lost my train of thought there. Say that again?")

            mouth.wait()  # let her finish before we start listening again
            arm_idle()
    finally:
        cancel_idle()
        brain.release()  # free the model on the way out (goodbye / Ctrl+C)


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
