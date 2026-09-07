"""Persistent, categorised memory — the facts FRIDAY carries between sessions.

Two separate concerns, deliberately:

- **Storage** is effectively unlimited. It lives in ``state/memory.json`` and
  holds everything FRIDAY has been told to remember, grouped into categories.
- **Prompt budget** is small. Only a compact "core" block (``memory_core_chars``,
  ~1000 chars) rides in the system prompt every turn. Everything else stays on
  disk and is pulled in on demand by the ``memory`` tool's ``recall`` action.

This is why a memory that "remembers everything" doesn't make every request
bigger and slower — the way a single flat block pasted into the prompt would.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock

CATEGORIES = ("identity", "preferences", "projects", "people", "misc")

_lock = Lock()


@dataclass
class Entry:
    value: str
    category: str
    added: str

    def line(self) -> str:
        return f"- ({self.category}) {self.value}"


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    # -- persistence ---------------------------------------------------
    def _read(self) -> dict[str, list[dict]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # -- reads --------------------------------------------------------
    def all_entries(self) -> list[Entry]:
        out: list[Entry] = []
        for cat, items in self._read().items():
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, dict) and it.get("value"):
                    out.append(Entry(it["value"], cat, it.get("added", "")))
        return out

    def is_empty(self) -> bool:
        return not self.all_entries()

    def search(self, query: str, limit: int = 8) -> list[Entry]:
        q = (query or "").lower().strip()
        entries = self.all_entries()
        if not q:
            return entries[:limit]
        terms = [t for t in q.split() if len(t) > 2] or [q]
        scored = []
        for e in entries:
            hay = e.value.lower()
            score = sum(hay.count(t) for t in terms)
            if score:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def core_block(self, max_chars: int = 1000) -> str:
        """The slice of memory that rides in the system prompt.

        All of ``identity`` (it's tiny and always relevant), then the most
        recent few from every other category, packed until the budget runs
        out. Newest first so a full budget still surfaces fresh facts.
        """
        by_cat: dict[str, list[Entry]] = {}
        for e in self.all_entries():
            by_cat.setdefault(e.category, []).append(e)

        ordered: list[Entry] = list(by_cat.get("identity", []))
        rest: list[Entry] = []
        for cat, items in by_cat.items():
            if cat == "identity":
                continue
            rest.extend(sorted(items, key=lambda e: e.added, reverse=True)[:5])
        rest.sort(key=lambda e: e.added, reverse=True)
        ordered.extend(rest)

        lines: list[str] = []
        used = 0
        for e in ordered:
            line = e.line()
            if used + len(line) + 1 > max_chars:
                break
            lines.append(line)
            used += len(line) + 1
        return "\n".join(lines)

    # -- writes -----------------------------------------------------
    def add(self, value: str, category: str = "misc") -> str:
        value = (value or "").strip()
        if not value:
            return ""
        category = category if category in CATEGORIES else "misc"
        with _lock:
            data = self._read()
            items = data.setdefault(category, [])
            if any(it.get("value", "").lower() == value.lower() for it in items):
                return category  # already known — no duplicate
            items.append({"value": value, "added": datetime.now().strftime("%Y-%m-%d")})
            self._write(data)
        return category

    def forget(self, query: str) -> list[str]:
        q = (query or "").lower().strip()
        if not q:
            return []
        removed: list[str] = []
        with _lock:
            data = self._read()
            for cat, items in list(data.items()):
                if not isinstance(items, list):
                    continue
                keep = []
                for it in items:
                    if q in it.get("value", "").lower():
                        removed.append(it["value"])
                    else:
                        keep.append(it)
                data[cat] = keep
            if removed:
                self._write(data)
        return removed
