"""FRIDAY's brain: a provider chain with tool use and rolling conversation memory.

Order of preference:

1. **Gemini** (cloud) — used when ``GEMINI_API_KEY`` is set.
2. **Ollama** (local) — the fallback. Tries each model in
   ``Config.ollama_models`` until one answers. Fully offline.

``Brain.ask()`` walks the chain: the first provider that returns a non-empty
answer wins, and only then is the exchange written to history. Each provider
runs its own tool-call loop — if the model asks for a tool, we run it (via the
``Toolbox``), feed the result back, and let the model continue, up to
``Config.max_tool_iterations`` rounds. If every provider fails it raises
``BrainError`` and the loop stays alive.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from dataclasses import dataclass

from .config import Config
from .persona import load_system_prompt
from .toolbox import Toolbox

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

    def generate(
        self,
        system: str,
        history: list[Turn],
        user_text: str,
        toolbox: Toolbox | None,
    ) -> str:
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

    def _tools_arg(self, toolbox: Toolbox | None):
        if not toolbox or not len(toolbox):
            return None
        types = self._types
        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=d["name"],
                        description=d["description"],
                        parameters_json_schema=d["parameters"],
                    )
                    for d in toolbox.declarations()
                ]
            )
        ]

    def generate(self, system, history, user_text, toolbox):
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

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._cfg.temperature,
            max_output_tokens=self._cfg.max_reply_tokens,
            tools=self._tools_arg(toolbox),
            http_options=types.HttpOptions(
                timeout=int(self._cfg.gemini_timeout * 1000)
            ),
        )

        resp = None
        for _ in range(self._cfg.max_tool_iterations):
            resp = self._client.models.generate_content(
                model=self._model, contents=contents, config=config
            )
            calls = resp.function_calls or []
            if not calls:
                break
            contents.append(resp.candidates[0].content)
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=c.name,
                            response={
                                "result": toolbox.call(c.name, dict(c.args or {}))
                            },
                        )
                        for c in calls
                    ],
                )
            )

        text = _clean(resp.text if resp else None)
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

        available = {m.model for m in self._client.list().models}
        if not available:
            raise BrainError(f"Ollama at {cfg.ollama_host} has no models")
        self._models = [m for m in self._models if m in available] or self._models

    @staticmethod
    def _tools_arg(toolbox: Toolbox | None):
        if not toolbox or not len(toolbox):
            return None
        return [
            {"type": "function", "function": d} for d in toolbox.declarations()
        ]

    def _run_model(self, model, base_messages, tools_arg, toolbox) -> str:
        messages = list(base_messages)
        resp = None
        for _ in range(self._cfg.max_tool_iterations):
            resp = self._client.chat(
                model=model,
                messages=messages,
                tools=tools_arg,
                think=False,
                options={
                    "temperature": self._cfg.temperature,
                    "num_predict": self._cfg.max_reply_tokens,
                },
            )
            calls = resp.message.tool_calls or []
            if not calls:
                break
            messages.append(resp.message)
            for call in calls:
                result = toolbox.call(
                    call.function.name, dict(call.function.arguments or {})
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": result,
                        "tool_name": call.function.name,
                    }
                )
        return _clean(resp.message.content if resp else None)

    def generate(self, system, history, user_text, toolbox):
        base = [{"role": "system", "content": system}]
        base += [{"role": t.role, "content": t.content} for t in history]
        base.append({"role": "user", "content": user_text})
        tools_arg = self._tools_arg(toolbox)

        last_error: Exception | None = None
        for model in self._models:
            try:
                text = self._run_model(model, base, tools_arg, toolbox)
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
    def __init__(self, cfg: Config, toolbox: Toolbox | None = None) -> None:
        self._cfg = cfg
        self._toolbox = toolbox
        self._system = load_system_prompt(cfg.persona_name)
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
        tools = f", {len(toolbox)} tools" if toolbox and len(toolbox) else ""
        print(f"  brain: {' -> '.join(p.name for p in self._providers)}{tools}")

    def ask(self, user_text: str) -> str:
        history = list(self._history)
        errors: list[str] = []
        for provider in self._providers:
            try:
                reply = provider.generate(
                    self._system, history, user_text, self._toolbox
                )
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
