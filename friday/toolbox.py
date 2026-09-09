"""Tool discovery and dispatch.

Every file in the ``tools/`` directory (see ``FRIDAY_TOOLS_DIR``) that defines
a ``TOOL`` dict and a ``run`` function becomes a tool the brain can call:

    TOOL = {
        "name": "get_time",
        "description": "Current time, optionally in another timezone.",
        "parameters": {                       # JSON Schema, an object
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "description": "IANA name, e.g. Asia/Tokyo"},
            },
            "required": [],
        },
    }

    def run(timezone: str = "") -> str:
        ...

``run`` is called with the arguments the model supplied, matched to its
signature by name. A tool may also declare ``notify`` in its signature to get
a ``Callable[[str], None]`` it can call to have FRIDAY say something later
(e.g. a timer going off) — the message is queued and spoken by the main loop.

A tool module may define ``on_load(notify)`` — called once at startup (for
enabled tools only). Use it to start a background checker, e.g. for reminders
that need to fire without the tool being called first.

Discovery happens once at startup. A file that fails to import, or is missing
``TOOL``/``run``, is skipped with a logged reason — it never breaks the others.

Destructive tools
-----------------
Two optional keys in the ``TOOL`` dict gate irreversible actions:

    "confirm": True                     # every call needs a spoken yes/no
    "confirm": {"action": ["clear"]}    # only when arg action is "clear"
    "mutates": {"action": ["add", "clear"]}   # snapshot state/ first (writes
                                              # only!), so "undo" works

When a confirmed call arrives, ``Toolbox.call`` parks it (``self.pending``) and
returns a string telling the model to ask the user out loud. ``Brain`` catches
the user's next turn: a clear yes runs the parked call, anything else drops it.
A module may also define ``confirm_prompt(**args) -> str`` for the phrasing.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import queue
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,47}$")


def _spec_matches(spec: "bool | dict", args: dict) -> bool:
    """``True`` -> always; ``{param: [values]}`` -> when an arg matches one."""
    if spec is True:
        return True
    if isinstance(spec, dict):
        for key, values in spec.items():
            got = str(args.get(key, "")).strip().lower()
            if got in {str(v).strip().lower() for v in values}:
                return True
    return False


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable
    source: str
    module: object = None
    confirm: "bool | dict" = False
    mutates: "bool | dict" = False

    def declaration(self) -> dict:
        """Provider-neutral JSON-Schema declaration."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters or {"type": "object", "properties": {}},
        }

    def needs_confirm(self, args: dict) -> bool:
        """Does a call with these args have to be confirmed out loud first?"""
        return _spec_matches(self.confirm, args)

    def will_mutate(self, args: dict) -> bool:
        """Does a call with these args change state/ (so snapshot it first)?"""
        return _spec_matches(self.mutates, args)


@dataclass
class PendingCall:
    """A destructive tool call, parked until the user confirms it."""

    name: str
    args: dict
    prompt: str


@dataclass
class _Snapshot:
    label: str
    files: dict  # filename -> bytes, a copy of state/ before a mutating call


class Toolbox:
    def __init__(
        self,
        tools_dir: Path,
        enabled: list[str] | None = None,
        confirm: bool = True,
    ) -> None:
        self._dir = tools_dir
        # None / empty  -> every discovered tool is enabled
        self._enabled = set(enabled) if enabled else None
        self._confirm = confirm
        self._tools: dict[str, Tool] = {}
        self._skipped: list[str] = []
        self.notifications: "queue.Queue[str]" = queue.Queue()
        self._pending: PendingCall | None = None
        self._undo: _Snapshot | None = None
        self._discover()

    # -- discovery ---------------------------------------------------------
    def _discover(self) -> None:
        if not self._dir.is_dir():
            return
        for path in sorted(self._dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                tool = self._load_one(path)
            except Exception as exc:  # noqa: BLE001 — one bad file mustn't sink the rest
                self._skipped.append(f"{path.name}: {exc}")
                continue
            if self._enabled is not None and tool.name not in self._enabled:
                continue
            self._tools[tool.name] = tool
            on_load = getattr(tool.module, "on_load", None)
            if callable(on_load):
                try:
                    on_load(self.notifications.put)
                except Exception as exc:  # noqa: BLE001 — a bad hook mustn't sink startup
                    self._skipped.append(f"{tool.source} on_load: {exc}")

    def _load_one(self, path: Path) -> Tool:
        spec = importlib.util.spec_from_file_location(f"friday_tool_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise ImportError("could not create import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        meta = getattr(module, "TOOL", None)
        run = getattr(module, "run", None)
        if not isinstance(meta, dict) or not callable(run):
            raise ValueError("missing TOOL dict or run() function")
        name = meta.get("name", "")
        if not _NAME_RE.match(name):
            raise ValueError(f"bad tool name {name!r} (want snake_case, <=48 chars)")
        params = meta.get("parameters") or {"type": "object", "properties": {}}
        if not isinstance(params, dict):
            raise ValueError("parameters must be a JSON-Schema dict")
        confirm = meta.get("confirm", False)
        mutates = meta.get("mutates", False)
        for key, val in (("confirm", confirm), ("mutates", mutates)):
            if not isinstance(val, (bool, dict)):
                raise ValueError(f"'{key}' must be true or a {{param: [values]}} dict")
        return Tool(
            name=name,
            description=str(meta.get("description", "")).strip(),
            parameters=params,
            run=run,
            source=path.name,
            module=module,
            confirm=confirm,
            mutates=mutates,
        )

    # -- accessors -------------------------------------------------------
    def __len__(self) -> int:
        return len(self._tools)

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    @property
    def skipped(self) -> list[str]:
        return list(self._skipped)

    def declarations(self) -> list[dict]:
        return [t.declaration() for t in self._tools.values()]

    def subset(self, names: list[str] | None) -> "Toolbox | _ToolboxView":
        """A view exposing only ``names`` to the model (calls still work for
        any tool). ``None`` returns the full toolbox unchanged."""
        if names is None:
            return self
        return _ToolboxView(self, set(names))

    # -- dispatch -------------------------------------------------------
    def call(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"(no such tool: {name})"
        if self._confirm and tool.needs_confirm(args):
            self._pending = PendingCall(
                name, dict(args), self._confirm_prompt(tool, args)
            )
            return (
                "CONFIRMATION REQUIRED — this was NOT run. Do not call any tool "
                "now. Say exactly this to the user and wait for their reply: "
                f'"{self._pending.prompt} Shall I go ahead?"'
            )
        return self._dispatch(tool, name, args)

    def _dispatch(self, tool: Tool, name: str, args: dict) -> str:
        if tool.will_mutate(args):
            self._snapshot(f"the {name} change")
        kwargs = self._match_kwargs(tool.run, args)
        try:
            result = tool.run(**kwargs)
        except Exception as exc:  # noqa: BLE001 — report, don't crash the loop
            traceback.print_exc()
            return f"(tool {name} failed: {exc})"
        if result is None:
            return "(done)"
        return result if isinstance(result, str) else json.dumps(result, default=str)

    def _confirm_prompt(self, tool: Tool, args: dict) -> str:
        fn = getattr(tool.module, "confirm_prompt", None)
        if callable(fn):
            try:
                got = fn(**self._match_kwargs(fn, args))
                if got:
                    return str(got).strip()
            except Exception:  # noqa: BLE001 — fall back to the generic phrasing
                pass
        detail = ", ".join(f"{k}={v}" for k, v in args.items() if v not in ("", None))
        return f"You want me to run {tool.name}" + (f" ({detail})." if detail else ".")

    # -- confirmation (the parked call) --------------------------------
    @property
    def pending(self) -> PendingCall | None:
        return self._pending

    def clear_pending(self) -> None:
        self._pending = None

    def resolve_pending(self, proceed: bool) -> str:
        """Run (or drop) the parked call. Returns what to say back."""
        pending, self._pending = self._pending, None
        if pending is None:
            return ""
        if not proceed:
            return "Okay — I'll leave that alone."
        tool = self._tools.get(pending.name)
        if tool is None:
            return "That's not something I can do anymore."
        return self._dispatch(tool, pending.name, pending.args)

    # -- undo (one level, state/ only) --------------------------------
    @staticmethod
    def _state_dir() -> Path:
        from friday.config import Config

        return Config().state_path

    def _snapshot(self, label: str) -> None:
        try:
            files = {p.name: p.read_bytes() for p in self._state_dir().glob("*.json")}
        except OSError:  # noqa: BLE001
            return
        self._undo = _Snapshot(label, files)

    def undo_last(self) -> str | None:
        """Restore the state/ files as they were before the last mutating call.
        Returns the line to speak, or None if there's nothing to undo."""
        snap, self._undo = self._undo, None
        if snap is None:
            return None
        try:
            for fname, blob in snap.files.items():
                (self._state_dir() / fname).write_bytes(blob)
        except OSError as exc:  # noqa: BLE001
            return f"I couldn't undo that — {exc}."
        return f"Done — I've reversed {snap.label}."

    def _match_kwargs(self, run: Callable, args: dict) -> dict:
        sig = inspect.signature(run)
        if any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values()):
            kwargs = dict(args)
        else:
            kwargs = {k: v for k, v in args.items() if k in sig.parameters}
        if "notify" in sig.parameters:
            kwargs["notify"] = self.notifications.put
        return kwargs

    def drain_notifications(self) -> list[str]:
        out: list[str] = []
        while True:
            try:
                out.append(self.notifications.get_nowait())
            except queue.Empty:
                return out


class _ToolboxView:
    """A read-through slice of a Toolbox — only some tools are advertised to
    the model, but ``call`` still delegates to the full toolbox."""

    def __init__(self, parent: Toolbox, names: set[str]) -> None:
        self._parent = parent
        self._names = names & set(parent.names)

    def __len__(self) -> int:
        return len(self._names)

    @property
    def names(self) -> list[str]:
        return [n for n in self._parent.names if n in self._names]

    def declarations(self) -> list[dict]:
        return [d for d in self._parent.declarations() if d["name"] in self._names]

    def call(self, name: str, args: dict) -> str:
        return self._parent.call(name, args)
