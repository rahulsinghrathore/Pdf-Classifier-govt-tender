"""Stage 6: heading levels (SPEC §6).

Level 1: lettered sections in capitals ("B. PRE-QUALIFICATION CRITERIA"), unlettered sections
whose label is a level-1 label (first on their page, before the annexures begin: f2 NIT, PQC, BRC,
ATC, LIST OF ANNEXURES), and Section / Part / Chapter. Level 2 + dots: Annexure N, N.M, N.M.K
(and Appendix, Schedule, Form, Format, Exhibit). Numbered clauses: dots + 3. Anything else is a
sub-heading one level below the innermost structural heading, so siblings share a level (f1
Annexure 3's "E." / "F." / "G."); an unnumbered title is never above level 3.
"""

from __future__ import annotations

from tender_sections.config import Settings
from tender_sections.models import Candidate
from tender_sections.scoring import in_capitals


def assign_levels(candidates: list[Candidate], settings: Settings | None = None) -> list[Candidate]:
    """Accepted candidates get a level, in document order.

    A titled line that is a bare id's looked-up title (f2 p58 "SCHEDULE OF RATES" under
    "Annexure 19") is consumed by that heading: rejected here, not a section of its own.
    """
    settings = settings or Settings()
    cfg = settings.levels
    consumed = _consumed_titles(candidates)
    anchor = 0  # level of the innermost structural heading: a section, an id, an emitted clause
    in_annexures = False  # an annexure-family heading is open under the current level-1 section
    previous: Candidate | None = None
    levelled = []
    for i, candidate in enumerate(candidates):
        if candidate.decision != "accept":
            levelled.append(candidate)
            continue
        if i in consumed:
            levelled.append(
                candidate.model_copy(update={"decision": "reject", "decided_by": "rules"})
            )
            continue
        level, structural = _level(candidate, anchor, in_annexures, previous, settings)
        candidate = candidate.model_copy(update={"level": level})
        levelled.append(candidate)
        if candidate.kind == "numeric" and not cfg.emit_numeric_clauses:
            continue  # internal clauses do not open a level for what follows
        if level == 1:
            in_annexures = False
        elif candidate.kind == "named":
            in_annexures = True
        if structural:
            anchor = level
        previous = candidate
    return levelled


def emitted(candidates: list[Candidate], settings: Settings | None = None) -> list[Candidate]:
    """The accepted headings that become sections; deeper ones stay in debug only."""
    cfg = (settings or Settings()).levels
    return [
        c
        for c in candidates
        if c.decision == "accept"
        and c.level is not None
        and c.level <= cfg.max_emit_level
        and (c.kind != "numeric" or cfg.emit_numeric_clauses)
    ]


def keyword(candidate: Candidate) -> str:
    """The named keyword of a named heading: "annexure_2_6_1" → "annexure"."""
    return (candidate.id_norm or "").split("_", 1)[0]


def _level(
    candidate: Candidate,
    anchor: int,
    in_annexures: bool,
    previous: Candidate | None,
    settings: Settings,
) -> tuple[int, bool]:
    """(level, structural): structural headings anchor the sub-headings that follow them."""
    cfg = settings.levels
    if candidate.kind == "named":
        if keyword(candidate) in cfg.level1_keywords:
            return 1, True
        return 2 + (candidate.id or "").count("."), True
    if candidate.kind == "numeric":
        return 3 + (candidate.id or "").count("."), True
    if candidate.kind == "letter" and in_capitals(candidate.title, settings):
        return 1, True
    if candidate.kind == "titled":
        if candidate.label in cfg.level1_labels and candidate.first_on_page and not in_annexures:
            return 1, True
        return max(3, anchor + 1), False
    if candidate.kind == "layout_only" and previous is not None and previous.kind == "layout_only":
        assert previous.level is not None
        step = previous.line.font_size - candidate.line.font_size
        if step >= cfg.layout_font_step:  # clearly smaller: one level deeper
            return previous.level + 1, False
        if -step >= cfg.layout_font_step:
            return max(anchor + 1, previous.level - 1), False
        return previous.level, False
    # A layout-only line, or a letter whose title is not in capitals.
    return anchor + 1, False


def _consumed_titles(candidates: list[Candidate]) -> set[int]:
    """Indexes of accepted titled lines that form an accepted bare id's title on the same page."""
    looked_up: dict[int, list[str]] = {}
    for c in candidates:
        if c.decision == "accept" and c.title_source == "lines_below":
            looked_up.setdefault(c.line.page, []).append(c.title)
    return {
        i
        for i, c in enumerate(candidates)
        if c.decision == "accept"
        and c.kind == "titled"
        and any(c.line.text in title for title in looked_up.get(c.line.page, []))
    }
