"""Stage 1: PDF → pages of logical lines (SPEC §3).

Lines are y-sorted and same-baseline fragments merged before anything else looks at them:
PyMuPDF block order is not reading order (f1 p52 returns "Definition:" before "Annexure 18").
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from tender_sections.config import IngestSettings, Settings
from tender_sections.models import (
    BBox,
    Bookmark,
    Line,
    Page,
    ParsedDocument,
    Table,
    TableRow,
    Warning,
)

# Otherwise find_tables() prints a package recommendation on stdout, into the CLI's JSON output.
if hasattr(pymupdf, "no_recommend_layout"):
    pymupdf.no_recommend_layout()

# Ligatures expanded so "speciﬁcation" matches the vocabulary; images are counted separately.
_TEXT_FLAGS = (
    pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES & ~pymupdf.TEXT_PRESERVE_LIGATURES
)

_CHAR_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u00ad": None,  # soft hyphen
        "\u200b": None,  # zero-width space / non-joiner / joiner, BOM
        "\u200c": None,
        "\u200d": None,
        "\ufeff": None,
    }
)


def normalize_text(text: str) -> str:
    """NFKC, straight quotes, invisible characters dropped, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFKC", text).translate(_CHAR_MAP).split())


def caps_ratio(text: str, min_letters: int) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < min_letters:
        return 0.0
    return sum(ch.isupper() for ch in letters) / len(letters)


def visible_chars(text: str) -> int:
    """Characters other than spaces (line text is already whitespace-collapsed)."""
    return len(text) - text.count(" ")


def body_font_size(lines: Iterable[Line], cfg: IngestSettings) -> float:
    """Character-weighted mode of line font sizes, bucketed; ties go to the smaller size.

    Weighted by characters rather than counted per line, so a page of one-word 8 pt table cells
    next to long 10 pt paragraphs still has a 10 pt body.
    """
    weight: Counter[float] = Counter()
    for line in lines:
        size = round(line.font_size / cfg.font_size_bucket) * cfg.font_size_bucket
        weight[size] += visible_chars(line.text)
    if not weight:
        return cfg.default_body_font_size
    return min(weight, key=lambda size: (-weight[size], size))


def assign_body_font_sizes(pages: list[Page], cfg: IngestSettings) -> list[Page]:
    """Each page's body size from its non-boilerplate lines; sparse pages take the document's.

    An annexure cover page (f2 pp58/69/79) holds nothing but its title, so the page's own mode is
    the title's 36 pt and the title could never look larger than the body.
    """
    content = [[line for line in page.lines if not line.is_boilerplate] for page in pages]
    document = body_font_size((line for lines in content for line in lines), cfg)
    return [
        page.model_copy(
            update={
                "body_font_size": body_font_size(lines, cfg)
                if sum(visible_chars(line.text) for line in lines) >= cfg.body_font_min_chars
                else document
            }
        )
        for page, lines in zip(pages, content, strict=True)
    ]


def ingest(pdf: bytes | str | Path, settings: Settings | None = None) -> ParsedDocument:
    settings = settings or Settings()
    cfg = settings.ingest
    if isinstance(pdf, str | Path):
        path = Path(pdf)
        data, file_name = path.read_bytes(), path.name
    else:
        data, file_name = pdf, None

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError(f"{file_name or 'PDF'} is password-protected")
        page_count = doc.page_count
        bookmarks = [
            Bookmark(level=level, title=normalize_text(title), page=page)
            for level, title, page in doc.get_toc(simple=True)
        ]
        pages = assign_body_font_sizes([_ingest_page(page, page_count, cfg) for page in doc], cfg)

    offset, warnings = _printed_page_offset(pages, cfg)
    return ParsedDocument(
        file_name=file_name,
        page_count=page_count,
        pages=pages,
        bookmarks=bookmarks,
        printed_page_offset=offset,
        warnings=warnings,
    )


@dataclass
class Fragment:
    """A run of text in points, in the displayed frame, before same-baseline merging: one PyMuPDF
    line, or one line an OCR engine read (ocr.py)."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    chars: int
    bold_chars: int

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _ingest_page(page: pymupdf.Page, page_count: int, cfg: IngestSettings) -> Page:
    width, height = page.rect.width, page.rect.height
    tables = _tables(page, width, height, cfg) if cfg.detect_tables else []
    boxes = [table.bbox for table in tables]
    lines = logical_lines(_fragments(page, cfg), page.number + 1, width, height, boxes, cfg)
    return Page(
        number=page.number + 1,
        width=width,
        height=height,
        printed_number=_printed_number(lines, page_count, cfg),
        body_font_size=cfg.default_body_font_size,  # set document-wide by assign_body_font_sizes
        lines=lines,
        image_count=len(page.get_image_info()),
        drawing_count=len(page.get_drawings()),
        tables=tables,
    )


def _tables(page: pymupdf.Page, width: float, height: float, cfg: IngestSettings) -> list[Table]:
    """Ruled tables with their rows; index detection reads (Number, Short Description) cells."""
    tables = []
    for found in page.find_tables().tables:
        if found.row_count < cfg.min_table_rows:
            continue
        rows = [
            TableRow(
                bbox=_normalize(row.bbox, width, height),
                cells=[normalize_text(cell or "") for cell in cells],
            )
            for row, cells in zip(found.rows, found.extract(), strict=False)
        ]
        tables.append(Table(bbox=_normalize(found.bbox, width, height), rows=rows))
    return tables


def _fragments(page: pymupdf.Page, cfg: IngestSettings) -> Iterator[Fragment]:
    """Lines in the displayed frame of the page, the frame of page.rect and find_tables().

    get_text() reports boxes and directions on the unrotated page. On a /Rotate page that frame
    differs: landscape content that reads upright on screen is vertical there, and its boxes
    would land in the wrong place.
    """
    m = page.rotation_matrix
    for block in page.get_text("dict", flags=_TEXT_FLAGS, sort=True)["blocks"]:
        if block.get("type") != 0:
            continue
        for raw in block["lines"]:
            dx, dy = raw["dir"]
            if abs(m.b * dx + m.d * dy) > cfg.max_line_slope:
                continue  # not horizontal on screen: stamps, watermarks, sideways tables
            text = normalize_text("".join(span["text"] for span in raw["spans"]))
            if not text:
                continue
            chars = bold_chars = 0
            size = 0.0
            for span in raw["spans"]:
                n = sum(not ch.isspace() for ch in span["text"])
                if not n:
                    continue
                chars += n
                size = max(size, span["size"])
                if span["flags"] & pymupdf.TEXT_FONT_BOLD or "bold" in span["font"].lower():
                    bold_chars += n
            x0, y0, x1, y1 = pymupdf.Rect(raw["bbox"]) * m
            yield Fragment(text, x0, y0, x1, y1, size, chars, bold_chars)


def logical_lines(
    fragments: Iterable[Fragment],
    page: int,
    width: float,
    height: float,
    tables: list[BBox],
    cfg: IngestSettings,
) -> list[Line]:
    """Fragments whose vertical centres differ by < ratio × font size form one line (rule 5).

    `page` is 1-based; width and height are the displayed page's, in points; tables are normalized.
    """
    groups: list[list[Fragment]] = []
    for frag in sorted(fragments, key=lambda f: (f.cy, f.x0)):
        if groups:
            anchor = groups[-1][0]
            if abs(frag.cy - anchor.cy) < cfg.merge_baseline_ratio * max(frag.size, anchor.size):
                groups[-1].append(frag)
                continue
        groups.append([frag])

    lines = []
    for order, group in enumerate(groups):
        parts = sorted(group, key=lambda f: f.x0)
        text = " ".join(part.text for part in parts)
        x0, y0, x1, y1 = _normalize(
            (
                min(p.x0 for p in parts),
                min(p.y0 for p in parts),
                max(p.x1 for p in parts),
                max(p.y1 for p in parts),
            ),
            width,
            height,
        )
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        lines.append(
            Line(
                page=page,
                text=text,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                font_size=round(max(p.size for p in parts), 2),
                bold_ratio=round(sum(p.bold_chars for p in parts) / sum(p.chars for p in parts), 3),
                caps_ratio=round(caps_ratio(text, cfg.caps_min_letters), 3),
                in_table=any(
                    tx0 <= cx <= tx1 and ty0 <= cy <= ty1 for tx0, ty0, tx1, ty1 in tables
                ),
                order=order,
            )
        )
    return lines


def _normalize(bbox: Iterable[float], width: float, height: float) -> BBox:
    x0, y0, x1, y1 = bbox
    return (
        min(max(x0 / width, 0.0), 1.0),
        min(max(y0 / height, 0.0), 1.0),
        min(max(x1 / width, 0.0), 1.0),
        min(max(y1 / height, 0.0), 1.0),
    )


def _printed_number(lines: list[Line], page_count: int, cfg: IngestSettings) -> int | None:
    """'Page X of N' when N is the document's page count, else a band line that is only a number.

    Nested series never count: f2's SOR carries its own 'SOR Page X of 10' on pp59–68.
    """
    bare: list[tuple[bool, float, int]] = []
    for line in lines:
        top = line.y0 < cfg.printed_number_top_band
        bottom = line.y1 > cfg.printed_number_bottom_band
        if not (top or bottom):
            continue
        for match in re.finditer(cfg.printed_page_of_n, line.text, re.IGNORECASE):
            if int(match.group(2)) == page_count:
                return int(match.group(1))
        if match := re.fullmatch(cfg.printed_page_bare, line.text):
            # Prefer the footer, then whichever line sits nearest the page edge.
            bare.append((bottom, line.y1 if bottom else -line.y0, int(match.group(1))))
    return max(bare)[2] if bare else None


def _printed_page_offset(
    pages: list[Page], cfg: IngestSettings
) -> tuple[int | None, list[Warning]]:
    diffs = [page.printed_number - page.number for page in pages if page.printed_number is not None]
    if not diffs:
        return None, []
    offset, count = Counter(diffs).most_common(1)[0]
    if count / len(diffs) >= cfg.printed_offset_min_agreement:
        return offset, []
    return None, [
        Warning(
            code="PRINTED_PAGE_INCONSISTENT",
            message=(
                f"printed page numbers follow no single offset "
                f"(most common {offset:+d} on {count} of {len(diffs)} numbered pages)"
            ),
        )
    ]
