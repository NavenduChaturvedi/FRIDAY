"""FRIDAY's brain: provider chain + per-request model routing + tool use.

For each turn:

1. ``router.classify()`` sorts the request into CHAT / COMPLEX / CODE.
2. Providers are tried in ``Config.brain_order`` (default: Ollama, then
   Gemini). Each provider picks its own model for that route:
     - Ollama:  qwen3.5:4b (chat) / gemma4 (complex) / qwen2.5-coder:14b (code),
                with ``ollama_models`` as the fallback list.
     - Gemini:  ``gemini_model`` (chat) / ``gemini_model_heavy`` (complex+code).
3. The chosen model runs a tool-call loop (up to ``max_tool_iterations``).
4. First provider to return non-empty text wins; only then is the exchange
   written to history. If all fail, ``BrainError`` — the loop stays alive.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from dataclasses import dataclass

from .config import Config
from .persona import load_system_prompt
from .router import Route, classify
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
        route: Route,
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

    def generate(self, system, history, user_text, toolbox, route):
        types = self._types
        model = self._cfg.gemini_model_for(route.value)
        print(f"  brain: {route.value} → gemini/{model}")

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
                model=model, contents=contents, config=config
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
        self._cfg = cfg

        self._available = {m.model for m in self._client.list().models}
        if not self._available:
            raise BrainError(f"Ollama at {cfg.ollama_host} has no models")

    def _model_order(self, route: Route) -> list[str]:
        routed = self._cfg.ollama_model_for(route.value)
        chain = [routed] + [m for m in self._cfg.ollama_models if m != routed]
        pulled = [m for m in chain if m in self._available]
        return pulled or chain  # if nothing matches, try the chain anyway

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

    def generate(self, system, history, user_text, toolbox, route):
        base = [{"role": "system", "content": system}]
        base += [{"role": t.role, "content": t.content} for t in history]
        base.append({"role": "user", "content": user_text})
        tools_arg = self._tools_arg(toolbox)

        order = self._model_order(route)
        print(f"  brain: {route.value} → ollama/{order[0]}")

        last_error: Exception | None = None
        for i, model in enumerate(order):
            try:
                text = self._run_model(model, base, tools_arg, toolbox)
                if text:
                    if i:
                        print(f"  brain: (fell back to ollama/{model})")
                    return text
                last_error = BrainError(f"{model} returned nothing")
            except Exception as exc:  # noqa: BLE001 — try the next model
                last_error = exc
            if i + 1 < len(order):
                print(
                    f"  brain: ollama/{model} didn't answer ({last_error}); "
                    f"trying ollama/{order[i + 1]}",
                    file=sys.stderr,
                )
        raise BrainError(f"all Ollama models failed ({last_error})")


_FACTORIES = {"gemini": GeminiProvider, "ollama": OllamaProvider}


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
        for key in cfg.brain_order:
            factory = _FACTORIES.get(key)
            if factory is None:
                print(f"  brain: unknown provider {key!r} in FRIDAY_BRAIN_ORDER",
                      file=sys.stderr)
                continue
            try:
                self._providers.append(factory(cfg))
            except Exception as exc:  # noqa: BLE001 — provider just isn't available
                print(f"  brain: {key} unavailable ({exc})", file=sys.stderr)

        if not self._providers:
            raise BrainError(
                "No brain available. Start Ollama (`ollama serve`) with a model "
                "pulled, or set GEMINI_API_KEY in .env."
            )
        tools = f", {len(toolbox)} tools" if toolbox and len(toolbox) else ""
        print(f"  brain: {' -> '.join(p.name for p in self._providers)}{tools}")

    def ask(self, user_text: str) -> str:
        route = classify(user_text)
        # A coding request rarely needs weather/timers/search, and the tool
        # schemas bloat the prompt — which the big code model is slowest to
        # chew through. Skip tools for CODE.
        toolbox = None if route is Route.CODE else self._toolbox
        history = list(self._history)
        errors: list[str] = []
        for provider in self._providers:
            try:
                reply = provider.generate(
                    self._system, history, user_text, toolbox, route
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
