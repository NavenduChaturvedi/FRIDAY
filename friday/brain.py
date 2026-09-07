"""FRIDAY's brain: a provider chain with rolling conversation memory.

Order of preference:

1. **Gemini** (cloud) — used when ``GEMINI_API_KEY`` is set. Fast, capable,
   the day-to-day driver.
2. **Ollama** (local) — the fallback. Tries each model in
   ``Config.ollama_models`` until one answers. Fully offline.

``Brain.ask()`` walks the chain: the first provider that returns a non-empty
answer wins, and only then is the exchange written to history. If every
provider fails it raises ``BrainError`` and the loop stays alive.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from dataclasses import dataclass

from .config import Config
from .persona import load_system_prompt

_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


class BrainError(RuntimeError):
    """Raised when no provider could produce a reply."""


@dataclass(frozen=True)
class Turn:
    role: str  # "user" | "assistant"
    content: str


def _clean(raw: str | None) -> str:
    if not raw:
        return ""
    return _THINK_BLOCK.sub("", raw).strip()


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
class Provider:
    name = "provider"

    def generate(self, system: str, history: list[Turn], user_text: str) -> str:
        raise NotImplementedError


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, cfg: Config) -> None:
        if not cfg.gemini_api_key:
            raise BrainError("GEMINI_API_KEY not set")

        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=cfg.gemini_api_key)
        self._model = cfg.gemini_model
        self._cfg = cfg

    def generate(self, system: str, history: list[Turn], user_text: str) -> str:
        types = self._types
        contents = [
            types.Content(
                role="model" if t.role == "assistant" else "user",
                parts=[types.Part(text=t.content)],
            )
            for t in history
        ]
        contents.append(
            types.Content(role="user", parts=[types.Part(text=user_text)])
        )

        resp = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=self._cfg.temperature,
                max_output_tokens=self._cfg.max_reply_tokens,
                http_options=types.HttpOptions(
                    timeout=int(self._cfg.gemini_timeout * 1000)
                ),
            ),
        )
        text = _clean(resp.text)
        if not text:
            raise BrainError("empty response from Gemini")
        return text


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, cfg: Config) -> None:
        import ollama

        self._client = ollama.Client(
            host=cfg.ollama_host, timeout=cfg.ollama_timeout
        )
        self._models = list(cfg.ollama_models)
        self._cfg = cfg

        # Fail fast (and loudly) if the server is down or the models are
        # missing, so we degrade to "no provider" cleanly at startup.
        available = {m.model for m in self._client.list().models}
        self._models = [m for m in self._models if m in available] or self._models
        if not available:
            raise BrainError(f"Ollama at {cfg.ollama_host} has no models")

    def generate(self, system: str, history: list[Turn], user_text: str) -> str:
        messages = [{"role": "system", "content": system}]
        messages += [{"role": t.role, "content": t.content} for t in history]
        messages.append({"role": "user", "content": user_text})

        last_error: Exception | None = None
        for model in self._models:
            try:
                resp = self._client.chat(
                    model=model,
                    messages=messages,
                    think=False,  # ignored by non-reasoning models
                    options={
                        "temperature": self._cfg.temperature,
                        "num_predict": self._cfg.max_reply_tokens,
                    },
                )
                text = _clean(resp["message"]["content"])
                if text:
                    return text
                last_error = BrainError(f"{model} returned nothing")
            except Exception as exc:  # noqa: BLE001 — try the next model
                last_error = exc
        raise BrainError(f"all Ollama models failed ({last_error})")


# --------------------------------------------------------------------------
# The chain
# --------------------------------------------------------------------------
class Brain:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._system = load_system_prompt(cfg.persona_name)
        # deque of Turns; maxlen keeps the last N exchanges (2 turns each).
        self._history: deque[Turn] = deque(maxlen=max(cfg.history_turns, 0) * 2)

        self._providers: list[Provider] = []
        for factory in (GeminiProvider, OllamaProvider):
            try:
                self._providers.append(factory(cfg))
            except Exception as exc:  # noqa: BLE001 — provider just isn't available
                print(f"  brain: {factory.name} unavailable ({exc})", file=sys.stderr)

        if not self._providers:
            raise BrainError(
                "No brain available. Set GEMINI_API_KEY in .env, or start "
                "Ollama (`ollama serve`) with a model pulled."
            )
        print(f"  brain: {' -> '.join(p.name for p in self._providers)}")

    def ask(self, user_text: str) -> str:
        history = list(self._history)
        errors: list[str] = []
        for provider in self._providers:
            try:
                reply = provider.generate(self._system, history, user_text)
            except Exception as exc:  # noqa: BLE001 — fall through to next provider
                errors.append(f"{provider.name}: {exc}")
                print(
                    f"  brain: {provider.name} failed ({exc}); falling back",
                    file=sys.stderr,
                )
                continue
            self._history.append(Turn("user", user_text))
            self._history.append(Turn("assistant", reply))
            return reply
        raise BrainError(" | ".join(errors) or "no providers")

    def reset(self) -> None:
        self._history.clear()
