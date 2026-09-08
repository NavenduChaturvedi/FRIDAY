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

    # --- Brain: provider order --------------------------------------------
    # Providers are tried in this order; the first to answer wins. Local
    # Ollama leads for now — flip to "gemini,ollama" once there's a paid key.
    brain_order: list[str] = field(
        default_factory=lambda: _env_list("FRIDAY_BRAIN_ORDER", ["ollama", "gemini"])
    )

    # --- Brain: Gemini ---------------------------------------------------
    # No key -> Gemini is skipped.
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    # "*-latest" aliases track the current model so the default doesn't rot.
    # gemini_model handles CHAT; gemini_model_heavy handles COMPLEX + CODE.
    gemini_model: str = field(
        default_factory=lambda: _env_str("FRIDAY_GEMINI_MODEL", "gemini-flash-latest")
    )
    gemini_model_heavy: str = field(
        default_factory=lambda: _env_str("FRIDAY_GEMINI_MODEL_HEAVY", "")
    )
    gemini_timeout: float = field(
        default_factory=lambda: _env_float("FRIDAY_GEMINI_TIMEOUT", 20.0)
    )

    # --- Brain: Ollama -------------------------------------------------
    ollama_host: str = field(
        default_factory=lambda: _env_str("OLLAMA_HOST", "http://localhost:11434")
    )
    # Model per request type (see friday/router.py). The routed model is tried
    # first; ollama_models is the fallback if it's unavailable or fails.
    ollama_model_chat: str = field(
        default_factory=lambda: _env_str("FRIDAY_OLLAMA_MODEL_CHAT", "qwen3.5:4b")
    )
    ollama_model_complex: str = field(
        default_factory=lambda: _env_str("FRIDAY_OLLAMA_MODEL_COMPLEX", "gemma4:latest")
    )
    ollama_model_code: str = field(
        default_factory=lambda: _env_str(
            "FRIDAY_OLLAMA_MODEL_CODE", "qwen2.5-coder:14b"
        )
    )
    ollama_models: list[str] = field(
        default_factory=lambda: _env_list(
            "FRIDAY_OLLAMA_MODELS",
            ["qwen3.5:4b", "gemma4:latest", "qwen2.5-coder:14b", "qwen2.5:3b"],
        )
    )
    ollama_timeout: float = field(
        default_factory=lambda: _env_float("FRIDAY_OLLAMA_TIMEOUT", 150.0)
    )
    # How long Ollama keeps a model in RAM after use. On a laptop, before
    # loading a heavy model (complex/code) FRIDAY unloads the *other* heavy
    # one — so at most the chat model plus one heavy model are ever resident.
    ollama_keep_alive: str = field(
        default_factory=lambda: _env_str("FRIDAY_OLLAMA_KEEP_ALIVE", "10m")
    )

    def gemini_model_for(self, route: str) -> str:
        heavy = self.gemini_model_heavy or self.gemini_model
        return self.gemini_model if route == "chat" else heavy

    def ollama_model_for(self, route: str) -> str:
        return {
            "chat": self.ollama_model_chat,
            "complex": self.ollama_model_complex,
            "code": self.ollama_model_code,
        }.get(route, self.ollama_model_chat)

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
    # How much of persistent memory rides in the system prompt each turn.
    memory_core_chars: int = field(
        default_factory=lambda: _env_int("FRIDAY_MEMORY_CORE_CHARS", 1000)
    )

    # --- Tools -------------------------------------------------------
    tools_dir: str = field(
        default_factory=lambda: _env_str("FRIDAY_TOOLS_DIR", "tools")
    )
    # Empty -> every tool in tools_dir is enabled.
    tools_enabled: list[str] = field(
        default_factory=lambda: _env_list("FRIDAY_TOOLS_ENABLED", [])
    )
    # CHAT requests see every enabled tool. COMPLEX gets only this handful —
    # enough for "look it up" without the 18-schema prompt bloat that makes
    # gemma4 recite the tool list. CODE gets none.
    complex_tools: list[str] = field(
        default_factory=lambda: _env_list(
            "FRIDAY_COMPLEX_TOOLS",
            ["get_time", "get_weather", "web_search", "wikipedia_lookup"],
        )
    )
    # Safety stop on a tool-call loop that never settles.
    max_tool_iterations: int = field(
        default_factory=lambda: _env_int("FRIDAY_MAX_TOOL_ITERATIONS", 4)
    )
    # Where tools keep local state (notes, reminders).
    state_dir: str = field(
        default_factory=lambda: _env_str("FRIDAY_STATE_DIR", "state")
    )

    # --- Persona -------------------------------------------------------
    persona_name: str = field(
        default_factory=lambda: _env_str("FRIDAY_PERSONA", "friday")
    )

    # --- Speech-to-text (faster-whisper) ---------------------------------
    # faster-whisper (CTranslate2) is CPU or NVIDIA-CUDA only — it can't use
    # this laptop's AMD NPU or iGPU. On CPU: tiny ~0.7s, base ~1.3s, small
    # ~3.8s for a 6s clip. base is the sweet spot; STT isn't the bottleneck.
    whisper_model: str = field(
        default_factory=lambda: _env_str("FRIDAY_WHISPER_MODEL", "base")
    )
    whisper_device: str = field(
        default_factory=lambda: _env_str("FRIDAY_WHISPER_DEVICE", "cpu")
    )
    whisper_compute_type: str = field(
        default_factory=lambda: _env_str("FRIDAY_WHISPER_COMPUTE", "int8")
    )
    # 0 = let CTranslate2 decide (usually fine). Bump toward the core count
    # if a bigger model feels sluggish.
    whisper_cpu_threads: int = field(
        default_factory=lambda: _env_int("FRIDAY_WHISPER_CPU_THREADS", 0)
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
    def state_path(self) -> Path:
        p = Path(self.state_dir)
        p = p if p.is_absolute() else REPO_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def memory_path(self) -> Path:
        return self.state_path / "memory.json"

    @property
    def piper_voice_path(self) -> Path:
        p = Path(self.piper_voice)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def piper_config_path(self) -> Path:
        p = self.piper_voice_path
        return p.with_name(p.name + ".json")

    def summary(self) -> str:
        order = [
            p for p in self.brain_order
            if p != "gemini" or self.gemini_api_key
        ]
        return (
            f"brain={'>'.join(order)}  "
            f"ollama[chat={self.ollama_model_chat}, "
            f"complex={self.ollama_model_complex}, code={self.ollama_model_code}]  "
            f"whisper={self.whisper_model}  voice={self.piper_voice_path.name}"
        )
