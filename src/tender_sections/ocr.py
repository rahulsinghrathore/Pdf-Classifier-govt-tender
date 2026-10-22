"""OCR for image-only pages, behind an interface (SPEC §3). Off by default.

Only a section that *starts* on an image-only page needs it: pages inside a section are covered by
the end-page rule (f2 pp84–85 fall inside Technical Specifications without OCR). Stage 2 decides
which pages need it; this module reads them and adds their lines. OCR lines go through the same
same-baseline merge as text-layer lines and carry no bold, so emphasis comes from their height
(font_size is the line's height in points) and from capitals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pymupdf
from PIL import Image

from tender_sections.boilerplate import reflag_boilerplate
from tender_sections.config import OCRSettings, Settings
from tender_sections.ingest import Fragment, logical_lines, normalize_text, visible_chars
from tender_sections.models import Line, Page, ParsedDocument, Warning


class OCRNotConfigured(RuntimeError):
    """OCR is off, or its engine is not installed."""


@dataclass(frozen=True)
class OCRWord:
    text: str
    left: float  # pixels of the rendered page
    top: float
    width: float
    height: float
    line: tuple[int, ...]  # words that share it were read as one line


class OCREngine(Protocol):
    def words(self, image: Image.Image) -> list[OCRWord]: ...


class TesseractEngine:
    """pytesseract's image_to_data. Needs `pip install -e '.[ocr]'` and the tesseract program."""

    def __init__(self, settings: OCRSettings) -> None:
        try:
            import pytesseract
        except ImportError as error:
            raise OCRNotConfigured(
                "pytesseract is not installed (pip install -e '.[ocr]')"
            ) from error
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError as error:
            raise OCRNotConfigured(
                "the tesseract program is not installed or not on PATH"
            ) from error
        self._tesseract = pytesseract
        self._settings = settings

    def words(self, image: Image.Image) -> list[OCRWord]:
        data = self._tesseract.image_to_data(
            image, lang=self._settings.languages, output_type=self._tesseract.Output.DICT
        )
        return [
            OCRWord(
                text=text.strip(),
                left=data["left"][i],
                top=data["top"][i],
                width=data["width"][i],
                height=data["height"][i],
                line=(data["block_num"][i], data["par_num"][i], data["line_num"][i]),
            )
            for i, text in enumerate(data["text"])
            if text.strip() and float(data["conf"][i]) >= self._settings.min_word_confidence
        ]


def ocr_engine(settings: OCRSettings) -> OCREngine:
    """The configured engine; OCRNotConfigured when OCR is off or cannot run here."""
    if not settings.enabled:
        raise OCRNotConfigured("OCR is off (ocr.enabled: false)")
    if settings.engine == "tesseract":
        return TesseractEngine(settings)
    raise OCRNotConfigured(f"the {settings.engine!r} OCR engine is not implemented; use tesseract")


def ocr_page(
    pix: pymupdf.Pixmap, page: Page, engine: OCREngine, settings: Settings | None = None
) -> list[Line]:
    """The lines an engine reads on one rendered page, merged and ordered like text-layer lines."""
    settings = settings or Settings()
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    scale = page.width / pix.width  # points per pixel
    by_line: dict[tuple[int, ...], list[OCRWord]] = {}
    for word in engine.words(image):
        by_line.setdefault(word.line, []).append(word)
    fragments = []
    for words in by_line.values():
        words.sort(key=lambda word: word.left)
        text = normalize_text(" ".join(word.text for word in words))
        if not text:
            continue
        x0, y0 = min(w.left for w in words) * scale, min(w.top for w in words) * scale
        x1 = max(w.left + w.width for w in words) * scale
        y1 = max(w.top + w.height for w in words) * scale
        fragments.append(Fragment(text, x0, y0, x1, y1, y1 - y0, visible_chars(text), 0))
    boxes = [table.bbox for table in page.tables]
    return logical_lines(fragments, page.number, page.width, page.height, boxes, settings.ingest)


def apply_ocr(
    doc: ParsedDocument,
    pdf: bytes | str | Path,
    settings: Settings | None = None,
    engine: OCREngine | None = None,
) -> ParsedDocument:
    """Read the pages stage 2 marked needs_ocr, add their lines, and find boilerplate again.

    A line the text layer already has (a running footer) is not added twice. When no engine can
    run, or one fails on a page, the page stays as it was, with warning OCR_UNAVAILABLE.
    """
    settings = settings or Settings()
    wanted = [page.number for page in doc.pages if page.needs_ocr]
    if not wanted:
        return doc
    warnings = list(doc.warnings)
    try:
        engine = engine or ocr_engine(settings.ocr)
    except OCRNotConfigured as error:
        message = f"pages {wanted} need OCR, but {error}; they stay image-only"
        return doc.model_copy(update={"warnings": [*warnings, _unavailable(message)]})

    data = Path(pdf).read_bytes() if isinstance(pdf, str | Path) else pdf
    pages = list(doc.pages)
    with pymupdf.open(stream=data, filetype="pdf") as source:
        for number in wanted:
            try:
                pix = source[number - 1].get_pixmap(dpi=settings.ocr.dpi)
                lines = ocr_page(pix, pages[number - 1], engine, settings)
            except Exception as error:  # a third-party engine: one page's failure is a warning
                message = f"OCR failed on page {number}: {type(error).__name__}: {error}"
                warnings.append(_unavailable(message, number))
                continue
            pages[number - 1] = _with_ocr_lines(pages[number - 1], lines)
    return reflag_boilerplate(
        doc.model_copy(update={"pages": pages, "warnings": warnings}), settings
    )


def _with_ocr_lines(page: Page, ocr: list[Line]) -> Page:
    """The page's own lines plus every OCR line whose centre no own line covers (the footer)."""

    def covered(line: Line) -> bool:
        cx, cy = (line.x0 + line.x1) / 2, (line.y0 + line.y1) / 2
        return any(o.x0 <= cx <= o.x1 and o.y0 <= cy <= o.y1 for o in page.lines)

    merged = sorted(
        [*page.lines, *(line for line in ocr if not covered(line))],
        key=lambda line: ((line.y0 + line.y1) / 2, line.x0),
    )
    lines = [line.model_copy(update={"order": order}) for order, line in enumerate(merged)]
    return page.model_copy(update={"lines": lines, "ocr": True})


def _unavailable(message: str, page: int | None = None) -> Warning:
    return Warning(code="OCR_UNAVAILABLE", message=message, page=page)
