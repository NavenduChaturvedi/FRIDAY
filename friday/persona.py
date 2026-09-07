"""Load FRIDAY's personality from editable markdown and build her system prompt.

A persona is a directory under ``personas/`` holding up to three files:

- ``SOUL.md``   — who she is, how she speaks, her hard rules
- ``MEMORY.md`` — things she should carry across sessions (facts about you)
- ``USER.md``   — who you are: name, pronouns, timezone, notes

All three are plain markdown you can edit by hand; changes take effect on the
next launch. Only ``SOUL.md`` is required. Each file is length-capped so a
runaway notes file can't crowd out the actual instructions.
"""

from __future__ import annotations

from pathlib import Path

from .config import REPO_ROOT

PERSONA_ROOT = REPO_ROOT / "personas"

# filename -> max characters folded into the prompt
_FILES: dict[str, int] = {
    "SOUL.md": 6000,
    "MEMORY.md": 2500,
    "USER.md": 1500,
}


def _read_capped(path: Path, cap: int) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    if len(text) > cap:
        text = text[:cap].rsplit(" ", 1)[0].rstrip() + " …"
    return text


def load_system_prompt(persona_name: str = "friday") -> str:
    """Concatenate the persona files for ``persona_name`` into one system prompt.

    Raises ``FileNotFoundError`` if the persona directory has no ``SOUL.md`` —
    without a soul there is no FRIDAY.
    """
    base = PERSONA_ROOT / persona_name
    sections: list[str] = []
    for filename, cap in _FILES.items():
        chunk = _read_capped(base / filename, cap)
        if chunk is not None:
            sections.append(chunk)

    if not sections or not (base / "SOUL.md").is_file():
        raise FileNotFoundError(
            f"No SOUL.md found for persona '{persona_name}' at {base}. "
            f"Expected {base / 'SOUL.md'}."
        )

    return "\n\n---\n\n".join(sections)
