"""Runtime configuration for F.R.I.D.A.Y.

Every knob lives here and is read exactly once, at import, from the process
environment. A ``.env`` file in the repo root is loaded first (via
python-dotenv) so secrets like ``GEMINI_API_KEY`` never have to be exported by
hand. See ``.env.example`` for the full list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / ".env")


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return items or list(default)


@dataclass(frozen=True)
class Config:
    """Immutable snapshot of every setting the app needs."""

    # --- Brain: Gemini (primary) --------------------------------------------
    # No key -> Gemini is skipped and FRIDAY runs entirely on local Ollama.
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    # "gemini-flash-latest" is an alias that always points at the current
    # flash model, so this default doesn't rot when a version is retired.
    gemini_model: str = field(
        default_factory=lambda: _env_str(
            "FRIDAY_GEMINI_MODEL", "gemini-flash-latest"
        )
    )
    gemini_timeout: float = field(
        default_factory=lambda: _env_float("FRIDAY_GEMINI_TIMEOUT", 20.0)
    )

    # --- Brain: Ollama (fallback) -----------------------------------------
    ollama_host: str = field(
        default_factory=lambda: _env_str("OLLAMA_HOST", "http://localhost:11434")
    )
    # Tried in order; first one that answers wins.
    ollama_models: list[str] = field(
        default_factory=lambda: _env_list(
            "FRIDAY_OLLAMA_MODELS", ["qwen2.5:3b", "qwen3.5:4b", "gemma4:latest"]
        )
    )
    ollama_timeout: float = field(
        default_factory=lambda: _env_float("FRIDAY_OLLAMA_TIMEOUT", 60.0)
    )

    # --- Brain: shared generation params --------------------------------
    max_reply_tokens: int = field(
        default_factory=lambda: _env_int("FRIDAY_MAX_REPLY_TOKENS", 400)
    )
    temperature: float = field(
        default_factory=lambda: _env_float("FRIDAY_TEMPERATURE", 0.7)
    )
    history_turns: int = field(
        default_factory=lambda: _env_int("FRIDAY_HISTORY_TURNS", 8)
    )

    # --- Tools -------------------------------------------------------
    tools_dir: str = field(
        default_factory=lambda: _env_str("FRIDAY_TOOLS_DIR", "tools")
    )
    # Empty -> every tool in tools_dir is enabled.
    tools_enabled: list[str] = field(
        default_factory=lambda: _env_list("FRIDAY_TOOLS_ENABLED", [])
    )
    # Safety stop on a tool-call loop that never settles.
    max_tool_iterations: int = field(
        default_factory=lambda: _env_int("FRIDAY_MAX_TOOL_ITERATIONS", 4)
    )

    # --- Persona -------------------------------------------------------
    persona_name: str = field(
        default_factory=lambda: _env_str("FRIDAY_PERSONA", "friday")
    )

    # --- Speech-to-text (faster-whisper) ---------------------------------
    whisper_model: str = field(
        default_factory=lambda: _env_str("FRIDAY_WHISPER_MODEL", "tiny")
    )
    whisper_device: str = field(
        default_factory=lambda: _env_str("FRIDAY_WHISPER_DEVICE", "cpu")
    )
    whisper_compute_type: str = field(
        default_factory=lambda: _env_str("FRIDAY_WHISPER_COMPUTE", "int8")
    )

    # --- Text-to-speech (Piper) ----------------------------------------
    # A bare filename is resolved against the repo root; an absolute path is
    # used as-is. The matching ``.onnx.json`` must sit next to the ``.onnx``.
    piper_voice: str = field(
        default_factory=lambda: _env_str(
            "FRIDAY_PIPER_VOICE", "en_GB-jenny_dioco-medium.onnx"
        )
    )

    # --- Audio capture -----------------------------------------------
    sample_rate: int = 16_000  # faster-whisper expects 16 kHz
    channels: int = 1
    chunk_size: int = 1024
    silence_threshold: float = field(
        default_factory=lambda: _env_float("FRIDAY_SILENCE_THRESHOLD", 0.03)
    )
    silence_duration: float = 1.5  # seconds of quiet that ends a turn
    min_speech_duration: float = 0.5  # ignore blips shorter than this
    max_recording_seconds: float = field(
        default_factory=lambda: _env_float("FRIDAY_MAX_RECORDING_SECONDS", 30.0)
    )

    # --- Loop control ------------------------------------------------
    exit_phrases: tuple[str, ...] = (
        "exit loop",
        "goodbye friday",
        "shut down friday",
        "power down friday",
    )

    @property
    def tools_path(self) -> Path:
        p = Path(self.tools_dir)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def piper_voice_path(self) -> Path:
        p = Path(self.piper_voice)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def piper_config_path(self) -> Path:
        p = self.piper_voice_path
        return p.with_name(p.name + ".json")

    def summary(self) -> str:
        brain = "gemini+ollama" if self.gemini_api_key else "ollama-only"
        return (
            f"brain={brain}  whisper={self.whisper_model}  "
            f"voice={self.piper_voice_path.name}  history={self.history_turns} turns"
        )
