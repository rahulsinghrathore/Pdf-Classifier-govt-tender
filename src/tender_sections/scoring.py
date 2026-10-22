"""Stage 5: 0–10 heading scores (SPEC §5c).

First pass: position, emphasis, pattern, listed, and the table / sentence penalties. Second pass,
in document order, against the headings accepted so far: letter_reuse and repeat_title.
score >= accept_at → accept, <= reject_at → reject, in between → undecided (the LLM's band),
except numbered clauses while they are not emitted: those are rejected without the LLM.
"""

from __future__ import annotations

import re

from tender_sections.candidates import emphasized
from tender_sections.config import ScoringSettings, Settings
from tender_sections.ingest import caps_ratio
from tender_sections.labels import OTHER, match_words
from tender_sections.models import Candidate, ParsedDocument, Warning


def score_candidates(
    candidates: list[Candidate], doc: ParsedDocument, settings: Settings | None = None
) -> list[Candidate]:
    settings = settings or Settings()
    cfg = settings.scoring
    listed = {entry.id_norm for entry in doc.index_entries}
    listed_letters = {id_norm for id_norm in listed if id_norm.startswith("sec_")}
    bookmarks = {match_words(bookmark.title) for bookmark in doc.bookmarks}
    body = {page.number: page.body_font_size for page in doc.pages}

    accepted: list[Candidate] = []
    level1_letters: set[str] = set()
    scored = []
    for candidate in candidates:
        breakdown = _first_pass(candidate, body[candidate.line.page], listed, bookmarks, settings)
        if (
            candidate.kind == "letter"
            and listed_letters
            and candidate.id_norm not in listed_letters
        ):
            breakdown["unlisted_letter"] = cfg.unlisted_letter  # f1 p27 "F. Applicability of …"
        if candidate.kind == "letter" and candidate.id in level1_letters:
            breakdown["letter_reuse"] = cfg.letter_reuse
        if accepted and _repeats(candidate, accepted[-1], cfg):
            breakdown["repeat_title"] = cfg.repeat_title
        score = _total(breakdown, cfg)
        if score >= cfg.accept_at:
            decision = "accept"
        elif score <= cfg.reject_at:
            decision = "reject"
        elif candidate.kind == "numeric" and not settings.levels.emit_numeric_clauses:
            # Option A: a clause that is never emitted cannot change the result; no LLM call.
            decision = "reject"
            breakdown["not_emitted"] = 0
        else:
            decision = "undecided"
        candidate = candidate.model_copy(
            update={
                "score": score,
                "score_breakdown": breakdown,
                "decision": decision,
                "decided_by": None if decision == "undecided" else "rules",
            }
        )
        if decision == "accept":
            accepted.append(candidate)
            if candidate.kind == "letter" and in_capitals(candidate.title, settings):
                level1_letters.add(candidate.id)
        scored.append(candidate)
    return scored


def reject_undecided(candidates: list[Candidate]) -> tuple[list[Candidate], list[Warning]]:
    """With the LLM disabled the 4–7 band is rejected, and one warning names the pages."""
    pages = sorted({c.line.page for c in candidates if c.decision == "undecided"})
    resolved = [
        c.model_copy(update={"decision": "reject", "decided_by": "disabled"})
        if c.decision == "undecided"
        else c
        for c in candidates
    ]
    if not pages:
        return resolved, []
    message = f"LLM disabled: undecided heading candidates rejected on pages {pages}"
    return resolved, [Warning(code="UNDECIDED_WITHOUT_LLM", message=message)]


def _first_pass(
    candidate: Candidate,
    body_font_size: float,
    listed: set[str],
    bookmarks: set[tuple[str, ...]],
    settings: Settings,
) -> dict[str, int]:
    cfg = settings.scoring
    line = candidate.line
    breakdown: dict[str, int] = {}
    if candidate.first_on_page:
        breakdown["first_on_page"] = cfg.first_on_page
    elif line.y0 < cfg.top_of_page_y:
        breakdown["top_of_page"] = cfg.top_of_page
    if emphasized(line, body_font_size, cfg):
        breakdown["emphasis"] = cfg.emphasis
    if pattern := _pattern(candidate, settings):
        breakdown["pattern"] = pattern
    if (candidate.id_norm is not None and candidate.id_norm in listed) or (
        candidate.title and match_words(candidate.title) in bookmarks
    ):
        breakdown["listed"] = cfg.listed
    if line.in_table or line.in_index_block:
        breakdown["in_table_or_index"] = cfg.in_table_or_index
    if _sentence_like(line.text, line.caps_ratio, cfg):
        breakdown["sentence_like"] = cfg.sentence_like
    return breakdown


def _pattern(candidate: Candidate, settings: Settings) -> int:
    cfg = settings.scoring
    if candidate.kind == "letter":
        if in_capitals(candidate.title, settings):
            return cfg.pattern_letter_caps
        if _title_case(candidate.title, cfg):
            return cfg.pattern_letter_title_case
        return cfg.pattern_letter_other
    return {
        "named": cfg.pattern_named,
        "titled": cfg.pattern_titled,
        "numeric": cfg.pattern_numeric,
        "layout_only": cfg.pattern_layout_only,
    }[candidate.kind]


def in_capitals(title: str, settings: Settings) -> bool:
    """A title in capitals: what makes a lettered heading a level-1 section."""
    min_letters = settings.ingest.caps_min_letters
    return caps_ratio(title, min_letters) >= settings.scoring.title_caps_ratio


def _title_case(title: str, cfg: ScoringSettings) -> bool:
    words = [word for word in re.findall(r"[A-Za-z]+", title) if len(word) >= 4]
    return bool(words) and sum(w[0].isupper() for w in words) / len(words) >= cfg.title_case_ratio


def _sentence_like(text: str, caps: float, cfg: ScoringSettings) -> bool:
    words = text.split()
    if len(text) > cfg.sentence_max_chars:
        return True
    if text.endswith(cfg.sentence_endings) or (
        words and words[-1].lower() in cfg.sentence_end_words
    ):
        return True
    return len(words) > cfg.sentence_max_words and caps < cfg.sentence_caps_ratio


def _repeats(candidate: Candidate, previous: Candidate, cfg: ScoringSettings) -> bool:
    """A title repeated within the window of the last accepted heading is not a new section.

    Only for a candidate without an id of its own: a numbered heading with a new id is a new
    section even when its label repeats (f1 Annexures 8, 9, 10 are all declarations).
    """
    if candidate.id_norm is not None and candidate.id_norm != previous.id_norm:
        return False
    if candidate.line.page - previous.line.page > cfg.repeat_window_pages:
        return False
    if candidate.label != OTHER and candidate.label == previous.label:
        return True
    return match_words(candidate.title or candidate.line.text) == match_words(
        previous.title or previous.line.text
    )


def _total(breakdown: dict[str, int], cfg: ScoringSettings) -> int:
    positive = min(sum(v for v in breakdown.values() if v > 0), cfg.max_score)
    negative = sum(v for v in breakdown.values() if v < 0)
    return max(0, min(cfg.max_score, positive + negative))
