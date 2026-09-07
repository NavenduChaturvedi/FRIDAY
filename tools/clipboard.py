"""Read or set the system clipboard."""

from __future__ import annotations

TOOL = {
    "name": "clipboard",
    "description": (
        "Read or write the system clipboard. action='read' for 'what's on my "
        "clipboard', 'what did I just copy'. action='write' with text for "
        "'copy this', 'put that on my clipboard'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["read", "write"]},
            "text": {"type": "string", "description": "for 'write': what to copy"},
        },
        "required": ["action"],
    },
}

_MAX_READ = 2000


def run(action: str = "read", text: str = "") -> str:
    try:
        import pyperclip
    except ImportError:
        return "Clipboard access isn't available — the pyperclip package isn't installed."

    action = (action or "read").strip().lower()

    if action == "write":
        if not text:
            return "What should I copy?"
        try:
            pyperclip.copy(text)
        except Exception as exc:  # noqa: BLE001
            return f"I couldn't write to the clipboard: {exc}"
        return "Copied."

    try:
        content = pyperclip.paste()
    except Exception as exc:  # noqa: BLE001
        return f"I couldn't read the clipboard: {exc}"
    if not content:
        return "The clipboard is empty."
    if len(content) > _MAX_READ:
        return f"Clipboard ({len(content)} chars): {content[:_MAX_READ]}… [truncated]"
    return f"Clipboard: {content}"
