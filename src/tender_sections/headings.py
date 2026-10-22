"""Structural heading patterns (SPEC §5b), shared by boilerplate, index blocks and candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Literal

from tender_sections.config import PatternSettings

HeadingKind = Literal["letter", "named", "numeric"]
ALL_KINDS: tuple[HeadingKind, ...] = ("letter", "named", "numeric")
STRUCTURAL: tuple[HeadingKind, ...] = ("letter", "named")


@dataclass(frozen=True)
class HeadingMatch:
    kind: HeadingKind
    id: str  # "B", "2.6.1", "IV", "29(A)"
    id_norm: str  # "sec_B", "annexure_2_6_1", "part_IV", "clause_29_A"
    display_id: str  # "B", "Annexure 2.6.1", "Part IV", "29(A)"
    title: str  # the text after the id; "" for a bare id


def match_heading(
    text: str, patterns: PatternSettings, kinds: tuple[HeadingKind, ...] = ALL_KINDS
) -> HeadingMatch | None:
    """The first of letter → named → numeric that matches at the start of the line."""
    if "letter" in kinds and (m := _compiled(patterns.letter).match(text)):
        return HeadingMatch("letter", m[1], f"sec_{m[1]}", m[1], m[2].strip())
    if "named" in kinds and (m := _compiled(patterns.named).match(text)):
        keyword, ident = m[1], m[2]
        display = f"{keyword.capitalize()} {ident}"
        return HeadingMatch("named", ident, named_id_norm(keyword, ident), display, m[3].strip())
    if "numeric" in kinds and (m := _compiled(patterns.numeric).match(text)):
        ident = m[1] + (m[2] or "")
        return HeadingMatch("numeric", ident, f"clause_{_slug(ident)}", ident, m[3].strip())
    return None


def is_structural(text: str, patterns: PatternSettings) -> bool:
    """A letter or named heading: never boilerplate, always a listed-id candidate."""
    return match_heading(text, patterns, STRUCTURAL) is not None


def named_id_norm(keyword: str, ident: str) -> str:
    """Normalized id: ("Annexure", "2.6.1") → "annexure_2_6_1", ("PART", "I") → "part_I"."""
    return f"{keyword.lower()}_{_slug(ident)}"


def _slug(ident: str) -> str:
    return re.sub(r"[^0-9A-Z]+", "_", ident.upper()).strip("_")


@cache
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)
