"""OCR behind its interface (SPEC §3). A scripted engine stands in for tesseract."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from PIL import Image

from fakes import FakeOCREngine, printed
from helpers import F2, expected, fixture_pdf
from pdfgen import Image as Picture
from pdfgen import Text, footer, make_pdf, paragraph
from tender_sections import extract
from tender_sections.boilerplate import mark_boilerplate
from tender_sections.config import OCRSettings, Settings
from tender_sections.ingest import ingest
from tender_sections.ocr import OCRNotConfigured, TesseractEngine, apply_ocr, ocr_engine

NIT = [Text(72, 100, "NOTICE INVITING TENDER", bold=True), *paragraph(140)]
SCANNED = [Picture((0, 0, 595, 842))]  # a scan: one image, no text layer
OCR_ON = Settings(ocr={"enabled": True, "dpi": 72})  # at 72 dpi a pixel is a point
BODY = [
    ("the contractor shall supply the material at site", 72, 130 + 14 * i, 10) for i in range(8)
]


def scc_scan(image: Image.Image) -> list:
    return [*printed(("SPECIAL CONDITIONS OF CONTRACT", 72, 90, 16)), *printed(*BODY, block=2)]


def codes(result) -> list[str]:
    return [warning.code for warning in result.warnings]


def test_without_ocr_a_scanned_page_falls_inside_the_section_before_it():
    result = extract(make_pdf([NIT, SCANNED]))
    assert result.flat_inclusive == {"nit": [1, 2]}
    assert ("PAGE_IMAGE_ONLY", 2) in [(w.code, w.page) for w in result.warnings]


def test_ocr_finds_a_section_that_starts_on_a_scanned_page():
    engine = FakeOCREngine(scc_scan)
    result = extract(make_pdf([NIT, SCANNED]), OCR_ON, ocr=engine)
    assert result.flat_inclusive == {"nit": [1, 1], "scc": [2, 2]}
    assert (result.targets["scc"], result.targets_status["scc"]) == ([2, 2], "found")
    assert (result.document.needs_ocr_pages, engine.sizes) == ([2], [(595, 842)])
    assert not {"PAGE_IMAGE_ONLY", "OCR_UNAVAILABLE"} & set(codes(result))


def test_ocr_lines_are_merged_and_measured_like_text_layer_lines():
    # Two boxes on one baseline are one line (CLAUDE.md hard rule 5); OCR reads no bold.
    def scan(image: Image.Image) -> list:
        return [
            *printed(("Annexure", 72, 90, 16)),
            *printed(("20", 160, 90, 16), block=2),
            *printed(*BODY, block=3),
        ]

    pdf = make_pdf([NIT, SCANNED])
    doc = apply_ocr(mark_boilerplate(ingest(pdf), OCR_ON), pdf, OCR_ON, FakeOCREngine(scan))
    page = doc.pages[1]
    first = page.lines[0]
    assert (page.ocr, page.is_image_only, first.text) == (True, True, "Annexure 20")
    assert (first.font_size, first.bold_ratio) == (16.0, 0.0)
    assert [line.order for line in page.lines] == list(range(1 + len(BODY)))
    assert page.body_font_size == 10.0


def test_a_line_the_text_layer_already_has_is_not_added_twice():
    pdf = make_pdf([NIT, [*SCANNED, footer("Page 2 of 2")]])

    def scan(image: Image.Image) -> list:
        return [*printed(*BODY), *printed(("Page 2 of 2", 72, 806, 10), block=2)]

    doc = apply_ocr(mark_boilerplate(ingest(pdf), OCR_ON), pdf, OCR_ON, FakeOCREngine(scan))
    texts = [line.text for line in doc.pages[1].lines]
    assert texts.count("Page 2 of 2") == 1
    assert len(texts) == 1 + len(BODY)
    assert [line.is_boilerplate for line in doc.pages[1].lines if line.text == "Page 2 of 2"] == [
        True
    ]


def test_without_an_engine_the_page_stays_and_a_warning_says_why(monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", None)  # import fails: not installed
    result = extract(make_pdf([NIT, SCANNED]), OCR_ON)
    assert result.flat_inclusive == {"nit": [1, 2]}
    (warning,) = [w for w in result.warnings if w.code == "OCR_UNAVAILABLE"]
    assert "pytesseract is not installed" in warning.message


def test_an_engine_failure_on_a_page_is_a_warning():
    def broken(image: Image.Image) -> list:
        raise RuntimeError("tesseract crashed")

    result = extract(make_pdf([NIT, SCANNED]), OCR_ON, ocr=FakeOCREngine(broken))
    assert result.flat_inclusive == {"nit": [1, 2]}
    assert [(w.code, w.page) for w in result.warnings if w.code.startswith("OCR")] == [
        ("OCR_UNAVAILABLE", 2)
    ]


def fake_tesseract(data: dict[str, list[Any]] | None = None, *, installed: bool = True):
    module = types.ModuleType("pytesseract")

    class TesseractNotFoundError(OSError):
        pass

    def get_tesseract_version() -> str:
        if not installed:
            raise TesseractNotFoundError()
        return "5.4.0"

    def image_to_data(image: Image.Image, lang: str, output_type: str) -> dict[str, list[Any]]:
        module.calls.append((lang, output_type))
        return data or {}

    module.TesseractNotFoundError = TesseractNotFoundError
    module.get_tesseract_version = get_tesseract_version
    module.image_to_data = image_to_data
    module.Output = types.SimpleNamespace(DICT="dict")
    module.calls = []
    return module


def test_the_tesseract_adapter_reads_image_to_data(monkeypatch):
    data = {
        "text": ["", "SPECIAL", "CONDITIONS", "smudge", "  "],
        "conf": [-1, 96, 91.5, 12, 95],
        "left": [0, 72, 160, 300, 0],
        "top": [0, 90, 90, 400, 0],
        "width": [595, 80, 110, 30, 5],
        "height": [842, 16, 16, 9, 5],
        "block_num": [0, 1, 1, 2, 2],
        "par_num": [0, 1, 1, 1, 1],
        "line_num": [0, 1, 1, 1, 1],
    }
    module = fake_tesseract(data)
    monkeypatch.setitem(sys.modules, "pytesseract", module)
    engine = ocr_engine(OCRSettings(enabled=True, languages="eng+hin"))
    words = engine.words(Image.new("RGB", (10, 10)))
    assert [(w.text, w.left, w.line) for w in words] == [
        ("SPECIAL", 72, (1, 1, 1)),
        ("CONDITIONS", 160, (1, 1, 1)),
    ]  # the page-level box, the empty word and the unsure "smudge" are dropped
    assert module.calls == [("eng+hin", "dict")]


def test_tesseract_without_its_program_is_not_configured(monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tesseract(installed=False))
    with pytest.raises(OCRNotConfigured, match="tesseract program"):
        TesseractEngine(OCRSettings(enabled=True))


def test_ocr_off_means_no_engine_and_only_tesseract_is_implemented():
    with pytest.raises(OCRNotConfigured, match="off"):
        ocr_engine(OCRSettings())
    with pytest.raises(OCRNotConfigured, match="not implemented"):
        ocr_engine(OCRSettings(enabled=True, engine="paddle"))


def test_f2_drawings_read_by_ocr_change_nothing():
    # pp84–85 are drawings inside Technical Specifications: an engine that finds no words there
    # leaves the ground truth as it was.
    engine = FakeOCREngine(lambda image: [])
    result = extract(fixture_pdf(F2), Settings(ocr={"enabled": True, "dpi": 72}), ocr=engine)
    assert (len(engine.sizes), result.document.needs_ocr_pages) == (2, [84, 85])
    assert result.flat_inclusive == expected(F2)["flat_inclusive"]
    assert result.flat_exclusive == expected(F2)["flat_exclusive"]
