"""Wake-word gating — so FRIDAY only answers when she's addressed.

Two modes, chosen automatically:

- **porcupine** — when ``PICOVOICE_ACCESS_KEY`` is set and ``pvporcupine`` is
  installed. A tiny always-on detector listens for the wake word (a Porcupine
  keyword like "jarvis"); the mic → Whisper → brain pipeline only runs once it
  fires, and a short chime acknowledges it.
- **filter** — otherwise. The pipeline runs on any speech as before, but a
  turn is dropped unless the transcript names her ("Friday, what's the time").
  The name is then stripped before the text goes to the brain.

``FRIDAY_WAKE_WORD=off`` disables gating entirely.
"""

from __future__ import annotations

import re
import struct
import sys

import numpy as np
import sounddevice as sd

from .config import Config

_OFF = {"", "off", "none", "false", "0"}
_PREFIXES = ("hey ", "ok ", "okay ", "yo ", "hi ")
# words that turn "<word> friday" into a date reference, not an address
_DATE_LEAD = {
    "on", "this", "next", "last", "by", "until", "till", "since", "before",
    "after", "come", "every",
}


class Wake:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self.word = cfg.wake_word.strip().lower()
        self.enabled = self.word not in _OFF
        self._porcupine = None
        self._keyword = None

        if self.enabled and cfg.picovoice_key:
            self._try_porcupine(cfg)

    def _try_porcupine(self, cfg: Config) -> None:
        try:
            import pvporcupine

            keyword = self.word if self.word in pvporcupine.KEYWORDS else "jarvis"
            self._porcupine = pvporcupine.create(
                access_key=cfg.picovoice_key,
                keywords=[keyword],
                sensitivities=[cfg.wake_sensitivity],
            )
            self._keyword = keyword
        except ImportError:
            print(
                "  wake: PICOVOICE_ACCESS_KEY is set but pvporcupine isn't "
                "installed — `pip install pvporcupine`. Using the filter.",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001 — bad key, unsupported platform…
            print(f"  wake: Porcupine unavailable ({exc}); using the filter",
                  file=sys.stderr)

    @property
    def mode(self) -> str:
        if not self.enabled:
            return "off"
        return "porcupine" if self._porcupine else "filter"

    @property
    def keyword(self) -> str:
        return self._keyword or self.word

    def describe(self) -> str:
        if self.mode == "porcupine":
            return f"porcupine → '{self._keyword}'"
        if self.mode == "filter":
            return f"filter → '{self.word}'"
        return "off (responds to everything)"

    # -- porcupine: block until the wake word ----------------------------
    def wait(self) -> None:
        pv = self._porcupine
        if pv is None:
            return
        try:
            with sd.RawInputStream(
                samplerate=pv.sample_rate,
                blocksize=pv.frame_length,
                dtype="int16",
                channels=1,
            ) as stream:
                while True:
                    data, _ = stream.read(pv.frame_length)
                    pcm = struct.unpack_from("h" * pv.frame_length, data)
                    if pv.process(pcm) >= 0:
                        self._chime()
                        return
        except Exception as exc:  # noqa: BLE001 — mic gone, etc.
            print(f"  wake: detector error ({exc}); passing through", file=sys.stderr)

    def _chime(self) -> None:
        rate = 16_000
        beep = np.concatenate([
            _tone(880, 0.08, rate),
            _tone(1320, 0.10, rate),
        ])
        try:
            sd.play(beep, samplerate=rate)
            sd.wait()
        except Exception:  # noqa: BLE001
            pass

    # -- filter: was she actually addressed? ---------------------------
    def addressed(self, transcript: str) -> bool:
        """True if the wake word is used as an address — near the front, or
        trailing on a short utterance ("what's the weather, Friday"). A stray
        "...on Friday" halfway through a long sentence doesn't count."""
        if self.mode != "filter":
            return True
        words = re.findall(r"[a-z']+", transcript.lower())
        if self.word not in words:
            return False
        i = words.index(self.word)
        if i > 0 and words[i - 1] in _DATE_LEAD:
            return False  # "on friday", "next friday" — a date, not a call
        lead = 2 + sum(1 for p in _PREFIXES if words[:1] == [p.strip()])
        return i < lead or (i >= len(words) - 1 and len(words) <= 5)

    def strip(self, transcript: str) -> str:
        """Drop a leading 'Friday,' / 'hey Friday' so the brain gets the ask."""
        if self.mode != "filter":
            return transcript
        pat = re.compile(
            r"^\s*(?:(?:" + "|".join(p.strip() for p in _PREFIXES) + r")\s+)?"
            + re.escape(self.word) + r"\b[\s,.:;—-]*",
            re.IGNORECASE,
        )
        return pat.sub("", transcript, count=1).strip() or transcript


def _tone(freq: float, secs: float, rate: int) -> np.ndarray:
    t = np.linspace(0, secs, int(rate * secs), endpoint=False)
    wave = 0.25 * np.sin(2 * np.pi * freq * t)
    fade = min(64, len(wave) // 4)
    if fade:
        wave[:fade] *= np.linspace(0, 1, fade)
        wave[-fade:] *= np.linspace(1, 0, fade)
    return (wave * 32767).astype(np.int16)
