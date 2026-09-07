"""Read a local text file so FRIDAY can answer questions about it."""

from __future__ import annotations

from pathlib import Path

TOOL = {
    "name": "read_file",
    "description": (
        "Read a text file from disk and return its contents, so you can "
        "summarise it or answer questions about it. Use for 'what's in "
        "notes.txt', 'summarise this README', 'read me my todo list'. Give a "
        "path — absolute, or relative to the user's home folder. Text files "
        "only; large files are truncated."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path, e.g. 'Documents/todo.md' or an absolute path.",
            },
        },
        "required": ["path"],
    },
}

_MAX_BYTES = 16_000
_TEXT_SUFFIXES = {
    "", ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".py", ".js", ".ts",
    ".tsx", ".jsx", ".html", ".css", ".sh", ".bat", ".ps1", ".sql", ".xml",
    ".env", ".gitignore",
}


def run(path: str = "") -> str:
    raw = (path or "").strip().strip('"').strip("'")
    if not raw:
        return "Which file?"

    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (Path.home() / p)
    try:
        p = p.resolve()
    except OSError:
        return f"That path doesn't look valid: {raw!r}"

    if not p.exists():
        return f"There's no file at {p}."
    if p.is_dir():
        return f"{p} is a folder, not a file. Try find_files to see what's in it."
    if p.suffix.lower() not in _TEXT_SUFFIXES:
        return f"{p.name} isn't a text file I can read."

    try:
        data = p.read_bytes()
    except PermissionError:
        return f"I don't have permission to read {p.name}."
    except OSError as exc:
        return f"I couldn't read {p.name}: {exc}"

    truncated = len(data) > _MAX_BYTES
    text = data[:_MAX_BYTES].decode("utf-8", errors="replace")
    note = "\n\n[...truncated]" if truncated else ""
    return f"Contents of {p.name}:\n\n{text}{note}"
