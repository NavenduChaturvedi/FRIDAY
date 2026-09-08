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

    # Horizontal rules ("---", "***", "___"), whether alone or leading a line.
    text = re.sub(r"^\s*([-*_])\1{2,}\s*", "", text, flags=re.MULTILINE)

    # Bold / italic markers, only when they wrap text — so "2 * 3" survives.
    text = re.sub(r"(\*\*|\*|__|_)(?=\S)(.+?)(?<=\S)\1", r"\2", text)

    # Stray bold markers left over from a split mid-emphasis (e.g. "**1.").
    text = re.sub(r"\*\*|__", "", text)

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


# A sentence ends on . ! ? … (or a run of them / an ellipsis), optionally
# followed by a closing quote or bracket, then whitespace. "3.5" and "$1.20"
# don't match — no space after the dot.
_SENTENCE_END = re.compile(r'[.!?…]+["\'”’)\]]*(?=\s)')

# Common abbreviations that end in "." but don't end a sentence.
_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "a.m", "p.m", "approx",
}


class SentenceStreamer:
    """Feed streamed text deltas in; get whole sentences out, ready for TTS.

    The model produces a reply token by token; this batches those tokens into
    sentences so speech can start on sentence one while the model is still
    writing sentence two. Call ``feed`` with each delta and speak whatever it
    returns; call ``flush`` at the end for the trailing fragment.
    """

    def __init__(self, min_chars: int = 3) -> None:
        self._buf = ""
        self._min = min_chars

    def _is_real_boundary(self, upto: str) -> bool:
        if len(upto.strip()) < self._min:
            return False
        # The token right before the "." — strip trailing sentence punctuation
        # and any markdown clinging to it.
        token = re.split(r"[\s(]", upto.rstrip('.!?…"\')]'))[-1]
        core = token.strip("*_#>~`-–—").lower()
        if not core or core in _ABBREV:
            return False
        if core.isdigit():  # "1." "2." — a numbered-list marker, not a sentence
            return False
        if len(core) == 1 and core.isalpha():  # "a." "I."
            return False
        return True

    def feed(self, delta: str) -> list[str]:
        self._buf += delta or ""
        out: list[str] = []
        search_from = 0
        while True:
            m = _SENTENCE_END.search(self._buf, search_from)
            if not m:
                break
            cut = m.end()
            if not self._is_real_boundary(self._buf[:cut]):
                search_from = cut
                continue
            out.append(self._buf[:cut].strip())
            self._buf = self._buf[cut:].lstrip()
            search_from = 0
        return out

    def flush(self) -> list[str]:
        tail, self._buf = self._buf.strip(), ""
        return [tail] if tail else []
