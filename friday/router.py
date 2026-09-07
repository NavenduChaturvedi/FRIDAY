"""Decide what kind of request this is, so the brain can pick the right model.

Three buckets:

- ``CODE``    — anything about programming: writing, debugging, explaining code,
                shell/git/regex, stack traces.
- ``COMPLEX`` — reasoning-heavy: explain *why*, analyse, compare, plan, design,
                walk through step by step, or just a long/involved prompt.
- ``CHAT``    — everything else. The default. Quick back-and-forth.

It's a cheap keyword pass, not a model call — a wrong guess just means a
slightly better- or worse-suited model answers, and the fallback chain still
applies.
"""

from __future__ import annotations

import re
from enum import Enum


class Route(str, Enum):
    CHAT = "chat"
    COMPLEX = "complex"
    CODE = "code"


_CODE = re.compile(
    r"""
    \b(
        code|coding|program(s|ming)?|script|snippet|function|method|class|
        variable|parameter|argument|compile|compiler|syntax|refactor|
        debug(ging)?|traceback|stack\s?trace|exception|segfault|
        null\s?pointer|regex|regular\s+expression|
        unit\s?tests?|pytest|linter|lint|
        api|endpoint|json|sql\s?query|
        async|await|thread|mutex|
        git|commit|rebase|merge\s?conflict|pull\s?request|
        npm|yarn|pip|cargo|maven|gradle|docker|kubernetes|kubectl|
        stdout|stderr|cli|
        python|javascript|typescript|golang|rust|kotlin|swift|
        c\+\+|c#|\.net|scala|haskell|bash|powershell|shell\s?script|
        react|node(\.js)?|django|flask|fastapi|numpy|pandas|
        leetcode|algorithm|big\s?o|data\s?structure
    )\b
    | \.(py|js|ts|tsx|jsx|rs|go|java|rb|cpp|cs|sh|sql|html|css)\b
    | ```
    """,
    re.IGNORECASE | re.VERBOSE,
)

_COMPLEX = re.compile(
    r"""
    \b(
        explain|why\s+(is|are|does|do|did|would|can|can't)|
        how\s+(does|do|did|would|could|should)\b|
        analy(se|ze|sis)|assess|evaluate|
        compare|comparison|versus|trade[\s-]?offs?|pros\s+and\s+cons|
        step[\s-]by[\s-]step|walk\s+me\s+through|break\s+(it|this)\s+down|
        think\s+(through|about)|reason\s+(through|about)|
        plan|strategy|strategi(se|ze)|road\s?map|
        design\s+(a|an|the)|architect(ure)?|
        summar(ise|ize)|in\s+detail|deep\s+dive|
        prove|derive|derivation|
        research|investigate|implications?
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_LONG_PROMPT_WORDS = 60


def classify(text: str) -> Route:
    if not text:
        return Route.CHAT
    if _CODE.search(text):
        return Route.CODE
    if _COMPLEX.search(text) or len(text.split()) >= _LONG_PROMPT_WORDS:
        return Route.COMPLEX
    return Route.CHAT
