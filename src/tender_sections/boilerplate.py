"""Stage 2: running headers/footers, then the text-layer decision (SPEC §4).

The order matters. "First line on the page" means the first content line, and a page holding
nothing but a footer has no text layer (f2 pp84–85: 42 chars of footer around a drawing).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Collection

from tender_sections.config import BoilerplateSettings, Settings
from tender_sections.headings import is_structural
from tender_sections.ingest import assign_body_font_sizes, visible_chars
from tender_sections.models import Band, BoilerplateGroup, Line, Page, ParsedDocument, Warning


def mark_boilerplate(doc: ParsedDocument, settings: Settings | None = None) -> ParsedDocument:
    """Flag running headers/footers (lines are kept), then decide text layer and image-only."""
    settings = settings or Settings()
    flagged, groups = _find_boilerplate(doc.pages, settings)
    warnings = list(doc.warnings)
    pages = []
    for page in doc.pages:
        lines = [
            line.model_copy(update={"is_boilerplate": True})
            if (line.page, line.order) in flagged
            else line
            for line in page.lines
        ]
        page = _decide_text_layer(page.model_copy(update={"lines": lines}), settings)
        if page.is_image_only and not settings.ocr.enabled:
            warnings.append(
                Warning(
                    code="PAGE_IMAGE_ONLY",
                    page=page.number,
                    message=(
                        f"page {page.number} has no text layer and OCR is disabled; "
                        "it falls inside whichever section surrounds it"
                    ),
                )
            )
        pages.append(page)
    return doc.model_copy(
        update={
            "pages": assign_body_font_sizes(pages, settings.ingest),
            "warnings": warnings,
            "boilerplate_groups": groups,
        }
    )


def reflag_boilerplate(doc: ParsedDocument, settings: Settings | None = None) -> ParsedDocument:
    """Running headers and footers found again once OCR has added lines (ocr.apply_ocr).

    The text-layer decisions stay: a page OCR has read is still image-only, with needs_ocr.
    """
    settings = settings or Settings()
    flagged, groups = _find_boilerplate(doc.pages, settings)
    pages = [
        page.model_copy(
            update={
                "lines": [
                    line.model_copy(update={"is_boilerplate": (line.page, line.order) in flagged})
                    for line in page.lines
                ]
            }
        )
        for page in doc.pages
    ]
    return doc.model_copy(
        update={
            "pages": assign_body_font_sizes(pages, settings.ingest),
            "boilerplate_groups": groups,
        }
    )


def lines_to_readmit(
    doc: ParsedDocument,
    label_for: Callable[[str], str | None],
    accepted_labels: Collection[str],
) -> list[Line]:
    """Re-admission rule (SPEC §4 step 6), run after scoring.

    A stripped running title that maps to a label no accepted section carries comes back once:
    its first occurrence, un-flagged, for the caller to score as a `titled` candidate. One line per
    label at most; on f2 it returns nothing because Annexures 20/21 carry scc and tech_spec.
    """
    readmit: list[Line] = []
    seen: set[str] = set()
    for group in doc.boilerplate_groups:
        label = label_for(group.text)
        if label in (None, "other") or label in accepted_labels or label in seen:
            continue
        seen.add(label)
        line = doc.pages[group.first_page - 1].lines[group.first_order]
        readmit.append(line.model_copy(update={"is_boilerplate": False}))
    return readmit


def _band(line: Line, cfg: BoilerplateSettings) -> Band | None:
    if line.y0 < cfg.top_band:
        return "top"
    if line.y1 > cfg.bottom_band:
        return "bottom"
    return None


def _find_boilerplate(
    pages: list[Page], settings: Settings
) -> tuple[set[tuple[int, int]], list[BoilerplateGroup]]:
    """(page, order) of every boilerplate line, and the repeated-text groups behind them.

    Keys are exact text (lower-cased, spacing ignored), never digit-normalized:
    that would merge "Annexure 2" / "Annexure 3" into one key. Letter and named headings are
    exempt; vocabulary titles are not (f2's "SPECIAL CONDITIONS OF CONTRACT" header must go).
    """
    cfg = settings.boilerplate
    page_numbers = [re.compile(p, re.IGNORECASE) for p in cfg.page_number_patterns]

    flagged: set[tuple[int, int]] = set()
    occurrences: dict[tuple[Band, str], list[Line]] = defaultdict(list)
    for page in pages:
        for line in page.lines:
            band = _band(line, cfg)
            if band is None or is_structural(line.text, settings.patterns):
                continue
            if any(p.search(line.text) for p in page_numbers):
                flagged.add((line.page, line.order))
            else:
                # Spacing ignored: fragment joins give "No. :" on f1 pp41–42, "No.:" elsewhere.
                occurrences[(band, re.sub(r"\s+", "", line.text.lower()))].append(line)

    groups = []
    for (band, _), lines in occurrences.items():
        seen_on = sorted({line.page for line in lines})
        if len(seen_on) < cfg.min_pages:
            continue
        flagged.update((line.page, line.order) for line in lines)
        first = lines[0]
        groups.append(
            BoilerplateGroup(
                band=band,
                text=first.text,
                pages=seen_on,
                first_page=first.page,
                first_order=first.order,
            )
        )
    groups.sort(key=lambda g: (g.first_page, g.first_order))
    return flagged, groups


def _decide_text_layer(page: Page, settings: Settings) -> Page:
    chars = sum(visible_chars(line.text) for line in page.lines if not line.is_boilerplate)
    has_text_layer = chars >= settings.text_layer.min_chars
    has_graphics = (
        page.image_count > 0 or page.drawing_count >= settings.text_layer.min_vector_paths
    )
    is_image_only = not has_text_layer and has_graphics
    return page.model_copy(
        update={
            "has_text_layer": has_text_layer,
            "is_image_only": is_image_only,
            "needs_ocr": is_image_only and settings.ocr.enabled,
        }
    )
