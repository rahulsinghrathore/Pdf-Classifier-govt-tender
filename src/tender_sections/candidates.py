"""Stage 4: heading candidates (SPEC §5b).

A non-boilerplate line is a candidate when it is a letter / named / numeric heading, a short
emphasized line whose text maps to the vocabulary (unlettered headings such as f2 "NOTICE INVITING
TENDER"), or an emphasized first line of a page. A bare id ("Annexure 19") takes its title from the
largest emphasized lines below it, then from the document's own index.

Never candidates: lower-case list items ("d) Schedule of Rates / Price Schedule / Price Basis",
f2 p14), an index caption that names no section ("Contents:", f1 p2), and vocabulary words in
plain body text ("clause 7.2 of GCC)."), which no score could accept without emphasis anyway.
"""

from __future__ import annotations

import re

from tender_sections.config import CandidateSettings, ScoringSettings, Settings
from tender_sections.headings import match_heading
from tender_sections.labels import OTHER, label_for, label_for_text
from tender_sections.models import Candidate, Line, Page, ParsedDocument


def find_candidates(doc: ParsedDocument, settings: Settings | None = None) -> list[Candidate]:
    settings = settings or Settings()
    descriptions: dict[str, str] = {}
    for entry in doc.index_entries:
        if entry.description:
            descriptions.setdefault(entry.id_norm, entry.description)
    candidates = []
    for page in doc.pages:
        content = [line for line in page.lines if not line.is_boilerplate]
        for i, line in enumerate(content):
            candidate = _candidate(line, i == 0, page, content[i + 1 :], descriptions, settings)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def _candidate(
    line: Line,
    first: bool,
    page: Page,
    below: list[Line],
    descriptions: dict[str, str],
    settings: Settings,
) -> Candidate | None:
    cfg = settings.candidates
    match = match_heading(line.text, settings.patterns)
    if match is not None:
        title, source = match.title, "same_line"
        if not title:
            title, source = _title_below(below, page, cfg), "lines_below"
        if not title:
            title, source = descriptions.get(match.id_norm, ""), "index"
        if not title:
            source = "none"
        return Candidate(
            line=line,
            kind=match.kind,
            id=match.id,
            id_norm=match.id_norm,
            display_id=match.display_id,
            title=title,
            title_source=source,
            label=label_for(title, descriptions.get(match.id_norm), settings.labels),
            first_on_page=first,
        )

    text = line.text
    if re.match(settings.patterns.list_item, text):
        return None
    titled_shape = len(text) <= cfg.titled_max_chars and len(text.split()) <= cfg.titled_max_words
    if titled_shape and emphasized(line, page.body_font_size, settings.scoring):
        label = label_for_text(text, settings.labels)
        if label != OTHER:
            return Candidate(
                line=line,
                kind="titled",
                title=text,
                title_source="same_line",
                label=label,
                first_on_page=first,
            )

    standout = (
        line.font_size >= page.body_font_size + cfg.layout_only_font_delta
        or line.bold_ratio >= cfg.layout_only_bold_ratio
    )
    caption = re.fullmatch(settings.index.title_pattern, text)
    if first and standout and not caption and len(text) <= cfg.layout_only_max_chars:
        return Candidate(
            line=line, kind="layout_only", title=text, title_source="same_line", first_on_page=True
        )
    return None


def emphasized(line: Line, body_font_size: float, cfg: ScoringSettings) -> bool:
    """Bold, larger than the body, or in capitals (SPEC §5c "emphasis")."""
    return (
        line.bold_ratio >= cfg.emphasis_bold_ratio
        or line.font_size >= body_font_size + cfg.emphasis_font_delta
        or line.caps_ratio >= cfg.emphasis_caps_ratio
    )


def _title_below(below: list[Line], page: Page, cfg: CandidateSettings) -> str:
    """The largest emphasized lines below a bare id, in the top half of the page.

    One group of consecutive lines at the largest size: f2 p69 gives "SPECIAL CONDTIONS OF" +
    "CONTRACT" (both 36 pt), f2 p58 the 36 pt "SCHEDULE OF RATES" far below the 14 pt id line.
    """
    pool = [
        line
        for line in below
        if line.y0 < cfg.title_below_max_y
        and not line.text.endswith((",", ";"))  # salutations and addresses: "To, Numaligarh …,"
        and (
            line.bold_ratio >= cfg.title_below_bold_ratio
            or line.font_size >= page.body_font_size + cfg.title_below_font_delta
        )
    ]
    if not pool:
        return ""
    largest = max(line.font_size for line in pool)
    group: list[Line] = []
    for line in pool:
        if abs(line.font_size - largest) <= cfg.title_below_size_tolerance:
            if group and line.order != group[-1].order + 1:
                break
            group.append(line)
        elif group:
            break
    return " ".join(line.text for line in group)
