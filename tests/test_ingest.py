"""Stage 1: ingest (SPEC §3)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

from helpers import F1, F2, FIXTURE_NAMES, expected, raw_doc
from pdfgen import A3_LANDSCAPE, Grid, Text, make_pdf
from tender_sections.ingest import caps_ratio, ingest, normalize_text


def texts(pdf: bytes, page: int = 1) -> list[str]:
    return [line.text for line in ingest(pdf).pages[page - 1].lines]


def index_of(texts: list[str], prefix: str) -> int:
    found = [i for i, text in enumerate(texts) if text.startswith(prefix)]
    assert found, f"no line starts with {prefix!r}"
    return found[0]


# Logical lines -----------------------------------------------------------------------------------


def test_lines_follow_y_not_content_stream_order():
    # Drawn bottom-first, like f1 p52 where block order puts "Definition:" before "Annexure 18".
    pdf = make_pdf(
        [
            [
                Text(72, 300, "Definition: Purchaser means NRL"),
                Text(72, 120, "Annexure 18", size=14, bold=True),
            ]
        ]
    )
    lines = ingest(pdf).pages[0].lines
    assert [line.text for line in lines] == ["Annexure 18", "Definition: Purchaser means NRL"]
    assert [line.order for line in lines] == [0, 1]


def test_same_baseline_fragments_merge_left_to_right():
    # f1 p25: "D." and "Benefits Under…" are separate fragments on one baseline.
    pdf = make_pdf(
        [[Text(300, 200.8, "Benefits Under The Policy", bold=True), Text(72, 200, "D.", bold=True)]]
    )
    (line,) = ingest(pdf).pages[0].lines
    assert line.text == "D. Benefits Under The Policy"
    assert line.bold_ratio == 1.0


def test_lines_on_different_baselines_stay_separate():
    pdf = make_pdf([[Text(72, 200, "first line of text"), Text(72, 213, "second line of text")]])
    assert texts(pdf) == ["first line of text", "second line of text"]


def test_coordinates_are_normalized_on_landscape_pages():
    # f2 p84 is landscape A3: never assume portrait.
    page = ingest(make_pdf([[Text(900, 700, "Drawing title block")]], size=A3_LANDSCAPE)).pages[0]
    (line,) = page.lines
    assert (page.width, page.height) == A3_LANDSCAPE
    assert line.x0 == pytest.approx(900 / 1191, abs=1e-3)
    assert line.y1 == pytest.approx(700 / 842, abs=0.01)
    assert 0 <= line.x0 < line.x1 <= 1 and 0 <= line.y0 < line.y1 <= 1


def test_font_size_bold_and_caps_ratio():
    pdf = make_pdf(
        [
            [
                Text(72, 100, "NOTICE INVITING TENDER", size=12, bold=True),
                Text(72, 140, "Notice inviting tender"),
            ]
        ]
    )
    heading, body = ingest(pdf).pages[0].lines
    assert (heading.font_size, heading.bold_ratio, heading.caps_ratio) == (12, 1.0, 1.0)
    assert (body.font_size, body.bold_ratio) == (10, 0.0)
    assert body.caps_ratio == pytest.approx(1 / 20, abs=1e-3)


def test_caps_ratio_needs_min_letters():
    assert caps_ratio("ABC", min_letters=4) == 0.0
    assert caps_ratio("A.B.C.D", min_letters=4) == 1.0


def test_normalize_text():
    raw = "Speci\ufb01cation\u00a0 for  RTA\u201927\u00ad "
    assert normalize_text(raw) == "Specification for RTA'27"


def test_body_font_size_is_character_weighted_mode():
    pdf = make_pdf(
        [
            [
                Text(72, 100, "Big Title", size=18),
                Text(72, 140, "a paragraph of ordinary body text " * 2),
                Text(72, 170, "8a", size=8),
                Text(72, 185, "8b", size=8),
            ]
        ]
    )
    assert ingest(pdf).pages[0].body_font_size == 10.0


def paragraph(y: float, lines: int, size: float = 10) -> list[Text]:
    text = "a paragraph of ordinary body text " * 2
    return [Text(72, y + i * (size + 4), text, size=size) for i in range(lines)]


def test_sparse_page_takes_the_document_body_size():
    # f2 pp58/69/79: an annexure cover page holding nothing but a 36 pt title.
    cover = [
        Text(72, 100, "Annexure 20", size=14, bold=True),
        Text(72, 300, "SPECIAL CONDTIONS OF", size=36),
        Text(72, 345, "CONTRACT", size=36),
    ]
    pages = [paragraph(100, 8), paragraph(100, 5, size=9), cover]
    # The dense 9 pt page keeps its own body size; the cover takes the document's 10 pt.
    assert [page.body_font_size for page in ingest(make_pdf(pages)).pages] == [10.0, 9.0, 10.0]


def test_lines_inside_ruled_tables_are_flagged():
    cells = [
        Text(80 + col * 150, 220 + row * 30, f"cell {row}{col}")
        for row in range(3)
        for col in range(2)
    ]
    pdf = make_pdf(
        [
            [
                Grid(72, 200, 150, 30, rows=3, cols=2),
                *cells,
                Text(72, 400, "Paragraph after the table"),
            ]
        ]
    )
    page = ingest(pdf).pages[0]
    (table,) = page.tables
    assert [row.cells for row in table.rows] == [[f"cell {r}0", f"cell {r}1"] for r in range(3)]
    in_table = {line.text: line.in_table for line in page.lines}
    assert in_table.pop("Paragraph after the table") is False
    assert in_table and all(in_table.values())


def test_one_row_frame_is_not_a_table():
    # f2 pp70–78 are drawn inside a page border that find_tables() reports as a 1-row table.
    pdf = make_pdf([[Grid(20, 20, 555, 800, rows=1, cols=1), Text(72, 300, "4. Scope of Work")]])
    page = ingest(pdf).pages[0]
    assert page.tables == []
    assert [line.in_table for line in page.lines] == [False]


def test_rotated_page_lines_are_in_the_displayed_frame():
    # get_text() reports a /Rotate 90 page unrotated: text that reads upright on screen is
    # vertical there. It must be kept, at its position on screen; sideways text is dropped.
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.set_rotation(90)
    page.insert_text(
        (60, 770), "SCHEDULE OF RATES", fontsize=12, rotate=90
    )  # on screen at (72, 60)
    page.insert_text((72, 300), "sideways on screen", fontsize=10)
    (line,) = ingest(doc.tobytes()).pages[0].lines
    assert line.text == "SCHEDULE OF RATES"
    assert line.x0 == pytest.approx(72 / 842, abs=0.005)
    assert line.y0 < 60 / 595 < line.y1  # the baseline sits inside the line, near the top


def test_text_layer_is_left_for_stage_2():
    page = ingest(make_pdf([[Text(72, 100, "anything at all")]])).pages[0]
    assert (page.has_text_layer, page.is_image_only, page.needs_ocr) == (None, None, None)


def test_ingest_prints_nothing_on_stdout(tmp_path):
    # find_tables() prints a one-time PyMuPDF recommendation on stdout unless told not to, which
    # would corrupt JSON piped out of the CLI. A fresh process, because it shows only once.
    pdf = tmp_path / "page.pdf"
    pdf.write_bytes(make_pdf([[Text(72, 100, "anything at all")]]))
    src = Path(__file__).resolve().parents[1] / "src"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from tender_sections.ingest import ingest; ingest(sys.argv[1])",
            str(pdf),
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(src)},
    )
    assert result.stdout == ""


# Printed page numbers ----------------------------------------------------------------------------


def test_printed_numbers_ignore_nested_series():
    # f2 pp59–68 carry "SOR Page X of 10" next to the document's own "Page X of 85".
    pages = [
        [
            Text(72, 300, "schedule body"),
            Text(360, 815, f"Tender: T1 Page {i} of 12"),
            *([Text(72, 815, f"SOR Page {i - 4} of 4")] if 5 <= i <= 8 else []),
        ]
        for i in range(1, 13)
    ]
    doc = ingest(make_pdf(pages))
    assert [page.printed_number for page in doc.pages] == list(range(1, 13))
    assert (doc.printed_page_offset, doc.warnings) == (0, [])


def test_page_x_of_another_total_is_not_a_page_number():
    doc = ingest(
        make_pdf([[Text(72, 300, "body"), Text(360, 815, f"Page {i} of 10")] for i in (1, 2, 3)])
    )
    assert [page.printed_number for page in doc.pages] == [None, None, None]
    assert doc.printed_page_offset is None


def test_printed_offset_from_bare_numbers():
    doc = ingest(
        make_pdf([[Text(72, 300, "body"), Text(290, 815, f"- {i + 2} -")] for i in range(1, 6)])
    )
    assert doc.printed_page_offset == 2


def test_inconsistent_printed_numbers_warn():
    doc = ingest(
        make_pdf([[Text(72, 300, "body"), Text(290, 815, str(n))] for n in (3, 9, 4, 17, 2)])
    )
    assert doc.printed_page_offset is None
    assert [warning.code for warning in doc.warnings] == ["PRINTED_PAGE_INCONSISTENT"]


# Fixtures (skipped until the PDFs are in tests/fixtures/) ------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_document_facts(name):
    doc, exp = raw_doc(name), expected(name)["document"]
    assert doc.page_count == len(doc.pages) == exp["pages"]
    assert bool(doc.bookmarks) is exp["has_bookmarks"]
    assert doc.printed_page_offset == exp["printed_page_offset"]


def test_f1_p52_annexure_18_comes_before_definition():
    page_texts = [line.text for line in raw_doc(F1).pages[51].lines]
    assert index_of(page_texts, "Annexure 18") < index_of(page_texts, "Definition")


def test_f1_p25_d_benefits_is_one_logical_line():
    page_texts = [line.text for line in raw_doc(F1).pages[24].lines]
    index_of(page_texts, "D. Benefits Under The Public Procurement Policy")


def test_f2_sor_footer_is_ignored_for_printed_numbers():
    pages = raw_doc(F2).pages
    assert [page.printed_number for page in pages[58:68]] == list(range(59, 69))
