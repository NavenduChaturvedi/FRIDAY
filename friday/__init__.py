"""F.R.I.D.A.Y. — a local, voice-driven assistant.

The package is split into small pieces so each engine can be understood and
swapped on its own:

- ``config``  — every tunable, read once from the environment / ``.env``
- ``persona`` — loads FRIDAY's personality from ``personas/friday/*.md``
- ``brain``   — the LLM: Gemini first, local Ollama as fallback, rolling history
- ``voice``   — microphone capture, faster-whisper STT, Piper TTS, playback
- ``text``    — strips markdown/emoji so the TTS doesn't read formatting aloud

``friday.py`` at the repo root wires them into one conversational loop.
"""

__all__ = ["__version__"]
__version__ = "0.2.0"
