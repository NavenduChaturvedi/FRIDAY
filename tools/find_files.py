"""Find files by name under a folder."""

from __future__ import annotations

import fnmatch
import os
import time
from pathlib import Path

TOOL = {
    "name": "find_files",
    "description": (
        "Search for files whose name matches a pattern, under the user's home "
        "folder or a folder they name. Use for 'find my resume', 'where's that "
        "budget spreadsheet', 'any pdfs in Downloads'. Returns matching paths "
        "with sizes and dates."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name or glob, e.g. 'resume', '*.pdf', 'budget*'.",
            },
            "folder": {
                "type": "string",
                "description": "Where to look; default is the home folder.",
            },
        },
        "required": ["name"],
    },
}

_MAX_HITS = 15
_MAX_SCAN = 40_000
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "AppData",
    "Library", ".cache", "$RECYCLE.BIN", "System Volume Information",
}


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def run(name: str = "", folder: str = "") -> str:
    pattern = (name or "").strip().strip('"').strip("'")
    if not pattern:
        return "Find what?"
    if not any(c in pattern for c in "*?["):
        pattern = f"*{pattern}*"

    base = Path(folder).expanduser() if folder.strip() else Path.home()
    if not base.is_absolute():
        base = Path.home() / base
    if not base.is_dir():
        return f"There's no folder at {base}."

    hits: list[Path] = []
    scanned = 0
    pat = pattern.lower()
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for f in files:
            scanned += 1
            if fnmatch.fnmatch(f.lower(), pat):
                hits.append(Path(root) / f)
                if len(hits) >= _MAX_HITS:
                    break
        if len(hits) >= _MAX_HITS or scanned > _MAX_SCAN:
            break

    if not hits:
        return f"No files matching {name!r} under {base}."

    lines = []
    for h in hits:
        try:
            st = h.stat()
            when = time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))
            lines.append(f"- {h}  ({_human_size(st.st_size)}, {when})")
        except OSError:
            lines.append(f"- {h}")
    more = " (more matches not shown)" if len(hits) >= _MAX_HITS else ""
    return f"Found {len(hits)} file(s){more}:\n" + "\n".join(lines)
