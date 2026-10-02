"""Manual excerpts for a question: plain keyword retrieval, no model needed.

The player's manual (``data/manual``) is split into its sections; the
sections sharing the most words with the question go to the model with it,
so answers rest on the game's own documentation.  Pure and cached.
"""

from __future__ import annotations

import re
from functools import lru_cache

from src.core import manual

MAX_SECTIONS = 3
MAX_CHARS = 7_000
_WORD = re.compile(r"[a-zäöüß0-9]{3,}", re.IGNORECASE)
_STOP = frozenset((
    "the and for with what how why when where which this that from have does can "
    "der die das und mit wie was warum wann wo welche welcher dies diese ist sind "
    "ein eine einen kann wird werden mein meine ich wir nicht oder auf von zum zur "
    "den dem des bei aus").split())


def _words(text: str) -> set:
    return {word.lower() for word in _WORD.findall(text)} - _STOP


@lru_cache(maxsize=len(manual.LANGUAGES))
def sections(language: str) -> tuple:
    """``(chapter, title, text, words)`` for every manual section."""
    out = []
    for chapter in manual.CHAPTERS:
        blocks = manual.chapter_blocks(chapter, language)
        current, title = [], chapter
        for block in blocks + [manual.Block("heading", "", 1)]:
            if block.kind == "heading" and block.level <= 3:
                if current:
                    text = "\n".join(manual.text_lines(current, 100))
                    out.append((chapter, title, text, frozenset(_words(text))))
                current, title = [block], manual.plain(block.text)
            else:
                current.append(block)
    return tuple(out)


def excerpts(question: str, language: str, chapter_hint: str | None = None) -> str:
    """The best-matching sections as one text block (empty without a match)."""
    language = language if language in manual.LANGUAGES else "en"
    wanted = _words(question)
    if not wanted:
        return ""
    scored = []
    for index, (chapter, title, text, words) in enumerate(sections(language)):
        score = len(wanted & words) + 0.5 * len(wanted & _words(title))
        if chapter == chapter_hint:
            score += 0.5
        if score > 0:
            scored.append((-score, index, title, text))
    scored.sort()
    parts, budget = [], MAX_CHARS
    for _score, _index, title, text in scored[:MAX_SECTIONS]:
        chunk = text[:budget]
        budget -= len(chunk)
        parts.append(chunk)
        if budget <= 0:
            break
    return ("Manual excerpts:\n" + "\n\n".join(parts)) if parts else ""
