"""FRIDAY's brain: provider chain + per-request model routing + tool use.

For each turn:

1. ``router.classify()`` sorts the request into CHAT / COMPLEX / CODE.
2. Providers are tried in ``Config.brain_order``. Each picks its model for
   that route (Ollama: qwen3.5:4b / gemma4 / qwen2.5-coder:14b; Gemini:
   ``gemini_model`` / ``gemini_model_heavy``).
3. The chosen model runs a tool-call loop (up to ``max_tool_iterations``).
4. ``stream_reply()`` yields the answer **one clean sentence at a time**, so
   speech can start before the model has finished writing. The first provider
   to produce text wins; the full reply is written to history.

If a provider fails before producing anything, the next is tried. If it drops
*mid-reply*, FRIDAY keeps the partial rather than starting over (and
double-speaking). If all fail, ``BrainError`` — the loop stays alive.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

from .config import Config
from .memory import MemoryStore
from .persona import load_system_prompt
from .router import Route, classify
from .text import SentenceStreamer, clean_text_for_speech
from .toolbox import Toolbox

_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)

# "Friday, remember that I'm vegetarian" — a direct instruction to store a
# fact. Small models don't reliably turn this into a memory tool call, and
# it's too important to leave to chance, so it's handled before the LLM.
# "remember to <do X>" is deliberately excluded — that's a reminder/task.
_REMEMBER = re.compile(
    r"^(?:friday[,\s]+)?(?:please\s+)?"
    r"(?:remember|note|don'?t\s+forget)\s+"
    r"(?:that\s+|this(?:\s+about\s+me)?[:,]?\s*)?"
    r"(?P<fact>(?!to\s)[^.].*)$",
    re.IGNORECASE,
)


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

    def stream(
        self,
        system: str,
        history: list[Turn],
        user_text: str,
        toolbox: Toolbox | None,
        route: Route,
    ) -> Iterator[str]:
        raise NotImplementedError

    def generate(self, system, history, user_text, toolbox, route) -> str:
        text = "".join(self.stream(system, history, user_text, toolbox, route))
        if not text.strip():
            raise BrainError(f"empty response from {self.name}")
        return text


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

    # Gemini is fast and sits last in the chain — no token streaming, just
    # hand the whole reply to the sentence splitter at once.
    def stream(self, system, history, user_text, toolbox, route):
        yield self.generate(system, history, user_text, toolbox, route)

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

        base_config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._cfg.temperature,
            max_output_tokens=self._cfg.max_reply_tokens,
            tools=self._tools_arg(toolbox),
            http_options=types.HttpOptions(
                timeout=int(self._cfg.gemini_timeout * 1000)
            ),
        )
        answer_config = base_config.model_copy(update={"tools": None})

        # Up to N tool rounds, then one forced answer with no tools on offer.
        resp = None
        prev_sig = None
        for _ in range(max(self._cfg.max_tool_iterations, 1)):
            resp = self._client.models.generate_content(
                model=model, contents=contents, config=base_config
            )
            calls = resp.function_calls or []
            if not calls:
                return self._require_text(resp)
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
            sig = tuple(sorted(f"{c.name}:{c.args}" for c in calls))
            if sig == prev_sig:
                break
            prev_sig = sig

        resp = self._client.models.generate_content(
            model=model, contents=contents, config=answer_config
        )
        return self._require_text(resp)

    @staticmethod
    def _require_text(resp) -> str:
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

        # The big models. Before loading one, unload any other — so a laptop
        # only ever holds the chat model plus one heavy model.
        self._heavy = {
            cfg.ollama_model_complex,
            cfg.ollama_model_code,
        } - {cfg.ollama_model_chat}

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

    def _make_room_for(self, model: str) -> None:
        """Keep the laptop to chat-model + one heavy model. Unload the rest of
        ours; never touch a model FRIDAY doesn't manage."""
        if model not in self._heavy:
            return
        try:
            loaded = {m.model for m in self._client.ps().models}
        except Exception:  # noqa: BLE001
            return
        for other in (loaded & self._heavy) - {model}:
            try:
                self._client.generate(model=other, keep_alive=0)
                print(f"  brain: unloaded ollama/{other} to free memory")
            except Exception:  # noqa: BLE001
                pass

    def _chat_stream(self, model: str, messages: list[dict], tools):
        return self._client.chat(
            model=model,
            messages=messages,
            tools=tools,
            think=False,
            stream=True,
            keep_alive=self._cfg.ollama_keep_alive,
            options={
                "temperature": self._cfg.temperature,
                "num_predict": self._cfg.max_reply_tokens,
            },
        )

    @staticmethod
    def _sig(tool_calls) -> tuple:
        return tuple(
            sorted(
                f"{tc.function.name}:{tc.function.arguments}" for tc in tool_calls
            )
        )

    def _stream_model(
        self, model: str, messages: list[dict], tools_arg, toolbox
    ) -> Iterator[str]:
        self._make_room_for(model)
        # Up to N tool-calling rounds, then — if the model still hasn't given a
        # plain answer — one final round with no tools on offer, so it has to
        # reply with what it's gathered. gemma4 is prone to calling tools
        # forever; this stops it running out the clock and falling through.
        prev_sig = None

        for _ in range(max(self._cfg.max_tool_iterations, 1)):
            content: list[str] = []
            tool_calls: list = []
            for chunk in self._chat_stream(model, messages, tools_arg):
                delta = chunk.message.content or ""
                if delta:
                    content.append(delta)
                    yield delta
                if chunk.message.tool_calls:
                    tool_calls.extend(chunk.message.tool_calls)

            if not tool_calls:
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(content),
                    "tool_calls": [
                        {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                messages.append(
                    {
                        "role": "tool",
                        "content": toolbox.call(
                            tc.function.name, dict(tc.function.arguments or {})
                        ),
                        "tool_name": tc.function.name,
                    }
                )

            sig = self._sig(tool_calls)
            if sig == prev_sig:
                break  # spinning on the same call — cut to the answer
            prev_sig = sig

        # Forced answer round: no tools on offer.
        for chunk in self._chat_stream(model, messages, None):
            delta = chunk.message.content or ""
            if delta:
                yield delta

    def stream(self, system, history, user_text, toolbox, route):
        base = [{"role": "system", "content": system}]
        base += [{"role": t.role, "content": t.content} for t in history]
        base.append({"role": "user", "content": user_text})
        tools_arg = self._tools_arg(toolbox)

        order = self._model_order(route)
        print(f"  brain: {route.value} → ollama/{order[0]}")

        last_error: Exception | None = None
        for i, model in enumerate(order):
            started = False
            try:
                for delta in self._stream_model(
                    model, list(base), tools_arg, toolbox
                ):
                    started = True
                    yield delta
            except Exception as exc:  # noqa: BLE001
                if started:
                    raise  # committed — let Brain keep the partial
                last_error = exc
            else:
                if started:
                    if i:
                        print(f"  brain: (used ollama/{model})")
                    return
                last_error = BrainError(f"{model} returned nothing")

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
        self._base_system = load_system_prompt(cfg.persona_name)
        self._memory = MemoryStore(cfg.memory_path)
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
        mem = "" if self._memory.is_empty() else f", {len(self._memory.all_entries())} memories"
        print(f"  brain: {' -> '.join(p.name for p in self._providers)}{tools}{mem}")

    @property
    def memory(self) -> MemoryStore:
        return self._memory

    def _system(self) -> str:
        core = self._memory.core_block(self._cfg.memory_core_chars)
        if not core:
            return self._base_system
        return (
            f"{self._base_system}\n\n---\n\n"
            f"## What you remember about the user\n\n{core}\n\n"
            "If they ask you to remember, forget, or recall something, use the "
            "`memory` tool."
        )

    def stream_reply(self, user_text: str) -> Iterator[str]:
        """Yield the reply one clean, speakable sentence at a time."""
        shortcut = self._try_remember_shortcut(user_text)
        if shortcut is not None:
            yield shortcut
            return

        route = classify(user_text)
        toolbox = self._tools_for(route)
        system = self._system()
        history = list(self._history)

        errors: list[str] = []
        for provider in self._providers:
            splitter = SentenceStreamer()
            raw: list[str] = []
            spoke = False
            dropped = False
            try:
                for delta in provider.stream(
                    system, history, user_text, toolbox, route
                ):
                    raw.append(delta)
                    for sentence in splitter.feed(delta):
                        clean = clean_text_for_speech(sentence)
                        if clean:
                            spoke = True
                            yield clean
            except Exception as exc:  # noqa: BLE001
                if not spoke:
                    errors.append(f"{provider.name}: {exc}")
                    print(
                        f"  brain: {provider.name} failed ({exc}); falling back",
                        file=sys.stderr,
                    )
                    continue
                dropped = True
                print(
                    f"  brain: {provider.name} dropped mid-reply ({exc})",
                    file=sys.stderr,
                )

            if not dropped:
                for sentence in splitter.flush():
                    clean = clean_text_for_speech(sentence)
                    if clean:
                        spoke = True
                        yield clean

            full = _clean("".join(raw))
            if full:
                self._history.append(Turn("user", user_text))
                self._history.append(Turn("assistant", full))
                return
            errors.append(f"{provider.name}: empty response")

        raise BrainError(" | ".join(errors) or "no providers")

    def ask(self, user_text: str) -> str:
        return " ".join(self.stream_reply(user_text)).strip()

    def _tools_for(self, route: Route):
        """Which tools this route may call. Each route gets a curated set — a
        small local model can't juggle all 18 schemas without losing track of
        message roles. CODE gets none; "all" in the config means everything."""
        if self._toolbox is None:
            return None
        if route is Route.CHAT:
            names = self._cfg.chat_tools
        elif route is Route.COMPLEX:
            names = self._cfg.complex_tools
        else:
            return None
        if not names or [n.lower() for n in names] == ["all"]:
            return self._toolbox
        return self._toolbox.subset(names)

    def reset(self) -> None:
        self._history.clear()

    def _try_remember_shortcut(self, user_text: str) -> str | None:
        m = _REMEMBER.match(user_text.strip())
        if not m:
            return None
        fact = m.group("fact").strip().rstrip(".").strip()
        if len(fact) < 3:
            return None
        self._memory.add(fact, "misc")
        reply = "Got it. That's in memory now."
        self._history.append(Turn("user", user_text))
        self._history.append(Turn("assistant", reply))
        return reply
