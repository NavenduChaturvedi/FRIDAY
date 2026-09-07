"""Turn a model's markdown-flavoured reply into something a TTS engine can read.

The brain often answers with markdown — bold, headers, bullet lists, links,
code fences, the odd emoji. Piper will happily read "asterisk asterisk" or
"grinning face" out loud. ``clean_text_for_speech`` strips all of that and
leaves plain spoken prose.
"""

from __future__ import annotations

import re

# Emoji / pictographs plus the variation selector (U+FE0F) and zero-width
# joiner (U+200D) that glue multi-codepoint emoji together.
_EMOJI = re.compile(
    "[️‍"
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF]"
)


def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""

    # Fenced code blocks: keep the code, drop the ``` markers.
    text = re.sub(r"```[a-zA-Z0-9_+-]*\n?", "", text)

    # Bold / italic markers, only when they wrap text — so "2 * 3" and a lone
    # "*" survive.
    text = re.sub(r"(\*\*|\*|__|_)(?=\S)(.+?)(?<=\S)\1", r"\2", text)

    # Headers: "### Title" -> "Title"
    text = re.sub(r"^\s{0,3}#+\s+", "", text, flags=re.MULTILINE)

    # List bullets at the start of a line: "- item" / "* item" / "+ item"
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)

    # Numbered lists: "1. First" -> "First"
    text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.MULTILINE)

    # Blockquote markers at line start; mid-line ">" (e.g. "a -> b") is left.
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)

    # Images: keep alt text, drop the path.
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)

    # Links: keep the visible text, drop the URL.
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

    # Inline code: keep the contents, drop the backticks.
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Emoji / pictographs and their zero-width glue.
    text = _EMOJI.sub("", text)

    # Collapse whitespace so Piper reads smoothly.
    return re.sub(r"\s+", " ", text).strip()
