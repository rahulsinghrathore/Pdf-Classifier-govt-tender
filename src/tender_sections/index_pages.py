"""Stage 3: contents and annexure-list blocks → index entries (SPEC §5a).

Lines inside a block get in_index_block, the −5 that keeps list rows from becoming headings; the
page's own title above the block (f1 p14 "D. TENDER ANNEXURES", f2 p17 "LIST OF ANNEXURES") does
not. Each entry keeps its description, the second source of a section's title and label, and its
applicability: a "not applicable" heading governs the rest of its page and the next index page.

Bare letters count as listed ids only under a contents-like title (f1 p2 "Contents:"): clause
tables such as f2's ATC (rows A–Q) use them too. Named ids (Annexure 19, Part II) always count.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from tender_sections.config import IndexSettings, Settings
from tender_sections.headings import STRUCTURAL, HeadingMatch, match_heading
from tender_sections.models import BBox, IndexEntry, Line, Page, ParsedDocument, TableRow

_BARE_LETTER = re.compile(r"([A-Z])[.)]?")


@dataclass
class _Row:
    display_id: str
    id_norm: str
    description: str | None
    y: float  # top of the row, normalized


def mark_index_blocks(doc: ParsedDocument, settings: Settings | None = None) -> ParsedDocument:
    settings = settings or Settings()
    cfg = settings.index
    entries: list[IndexEntry] = []
    pages: list[Page] = []
    not_applicable_carried = False
    previous_index_page = None
    for page in doc.pages:
        found = _index_block(page, settings)
        if found is None:
            pages.append(page)
            continue
        blocks, rows = found
        if previous_index_page != page.number - 1:
            not_applicable_carried = False
        not_applicable_y = _not_applicable_heading(page, cfg)
        for row in rows:
            governed = not_applicable_carried or (
                not_applicable_y is not None and row.y > not_applicable_y
            )
            entries.append(
                IndexEntry(
                    id_norm=row.id_norm,
                    display_id=row.display_id,
                    description=row.description,
                    applicability=_applicability(row.description, governed, cfg),
                    page=page.number,
                )
            )
        not_applicable_carried = not_applicable_carried or not_applicable_y is not None
        previous_index_page = page.number
        pages.append(_mark(page, blocks))
    return doc.model_copy(update={"pages": pages, "index_entries": entries})


def _index_block(page: Page, settings: Settings) -> tuple[list[BBox], list[_Row]] | None:
    """Block bboxes and listed rows if the page is an index page, by table first, then by lines."""
    cfg = settings.index
    titled = _has_index_title(page, cfg)
    minimum = cfg.min_entries_with_title if titled else cfg.min_entries

    hits: list[tuple[BBox, list[_Row]]] = []
    for table in page.tables:
        rows = [row for raw in table.rows if (row := _table_row(raw, titled, settings))]
        descriptions = [len(row.description) for row in rows if row.description]
        if rows and statistics.median(descriptions or [0]) <= cfg.max_description_chars:
            hits.append((table.bbox, rows))
    if sum(len(rows) for _, rows in hits) >= minimum:
        return [bbox for bbox, _ in hits], [row for _, rows in hits for row in rows]
    return _line_block(page, titled, minimum, settings)


def _table_row(raw: TableRow, titled: bool, settings: Settings) -> _Row | None:
    """(id, description) from a row whose first non-empty cell, after an optional serial
    number, is a listed id."""
    filled = [(i, cell) for i, cell in enumerate(raw.cells) if cell]
    if len(filled) > 1 and re.fullmatch(settings.index.serial_cell_pattern, filled[0][1]):
        filled = filled[1:]  # "1 | Annexure 1 | Instructions to Bidders"
    if not filled:
        return None
    first, id_cell = filled[0]
    rest = next((cell for i, cell in filled if i > first), None)
    if titled and (m := _BARE_LETTER.fullmatch(id_cell)):
        return _Row(m[1], f"sec_{m[1]}", _description(rest, settings.index), raw.bbox[1])
    match = match_heading(id_cell, settings.patterns, ("named",))
    if match is None:
        return None
    description = rest if rest is not None else match.title or None
    return _Row(
        match.display_id, match.id_norm, _description(description, settings.index), raw.bbox[1]
    )


def _line_block(
    page: Page, titled: bool, minimum: int, settings: Settings
) -> tuple[list[BBox], list[_Row]] | None:
    """Fallback for lists that are not ruled tables: short id lines sharing a left edge."""
    cfg = settings.index
    kinds = STRUCTURAL if titled else ("named",)
    listed = [
        (line, match)
        for line in page.lines
        if not line.is_boilerplate
        and len(line.text) <= cfg.line_max_chars
        and (match := match_heading(line.text, settings.patterns, kinds))
    ]
    clusters: list[list[tuple[Line, HeadingMatch]]] = []
    for item in sorted(listed, key=lambda item: item[0].x0):
        if clusters and item[0].x0 - clusters[-1][0][0].x0 <= cfg.line_edge_tolerance:
            clusters[-1].append(item)
        else:
            clusters.append([item])
    best = max(clusters, key=len, default=[])
    if len(best) < minimum:
        return None
    lines = [line for line, _ in best]
    top, bottom = min(line.y0 for line in lines), max(line.y1 for line in lines)
    bbox = (min(line.x0 for line in lines), top, 1.0, bottom)
    rows = [
        _Row(m.display_id, m.id_norm, _description(m.title or None, cfg), line.y0)
        for line, m in sorted(best, key=lambda item: item[0].order)
    ]
    return [bbox], rows


def _has_index_title(page: Page, cfg: IndexSettings) -> bool:
    return any(
        not line.is_boilerplate and not line.in_table and re.fullmatch(cfg.title_pattern, line.text)
        for line in page.lines
    )


def _not_applicable_heading(page: Page, cfg: IndexSettings) -> float | None:
    """Top of the first 'not applicable' line outside the tables, if any."""
    ys = [
        line.y0
        for line in page.lines
        if not line.is_boilerplate
        and not line.in_table
        and re.search(cfg.not_applicable_pattern, line.text)
    ]
    return min(ys, default=None)


def _description(text: str | None, cfg: IndexSettings) -> str | None:
    if not text or re.fullmatch(cfg.empty_description_pattern, text):
        return None  # f2 Annexure 17 is listed with the description "None"
    return text


def _applicability(description: str | None, governed: bool, cfg: IndexSettings) -> str:
    if governed:
        return "not_applicable"
    if description is None or re.search(cfg.external_pattern, description):
        return "external"
    return "applicable"


def _mark(page: Page, blocks: list[BBox]) -> Page:
    def inside(line: Line) -> bool:
        cx, cy = (line.x0 + line.x1) / 2, (line.y0 + line.y1) / 2
        return any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in blocks)

    lines = [
        line.model_copy(update={"in_index_block": True}) if inside(line) else line
        for line in page.lines
    ]
    return page.model_copy(update={"lines": lines, "is_index_page": True})
