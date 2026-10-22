"""Stage 2: running headers/footers and the text-layer decision (SPEC §4)."""

from __future__ import annotations

import re

import pytest

from helpers import F1, F2, FIXTURE_NAMES, expected, marked_doc
from pdfgen import Image, Strokes, Text, footer, header, make_pdf
from tender_sections.boilerplate import lines_to_readmit, mark_boilerplate
from tender_sections.config import Settings
from tender_sections.ingest import ingest
from tender_sections.models import ParsedDocument


def marked(pages, settings: Settings | None = None) -> ParsedDocument:
    return mark_boilerplate(ingest(make_pdf(pages)), settings)


def flagged(doc: ParsedDocument) -> set[tuple[int, str]]:
    return {
        (line.page, line.text) for page in doc.pages for line in page.lines if line.is_boilerplate
    }


def first_content_line(doc: ParsedDocument, page: int) -> str:
    return next(line.text for line in doc.pages[page - 1].lines if not line.is_boilerplate)


# Running headers and footers ---------------------------------------------------------------------


def test_text_repeated_in_a_band_on_min_pages_is_boilerplate():
    pages = [[header("NRL Tender Ref. No: PUR1"), Text(72, 300, f"body {i}")] for i in range(3)]
    pages.append([Text(72, 300, "the header changes from here on")])  # as on f1 p14
    assert flagged(marked(pages)) == {(p, "NRL Tender Ref. No: PUR1") for p in (1, 2, 3)}


def test_text_on_fewer_pages_is_kept():
    pages = [[header("Draft for discussion"), Text(72, 300, "body")] for _ in range(2)]
    assert flagged(marked(pages)) == set()


def test_repeats_are_exact_text_not_digit_normalized():
    # Normalizing digits would merge "Copy 1", "Copy 2", … (and Annexure 2 / Annexure 3).
    pages = [[header(f"Copy {i}"), Text(72, 300, "body")] for i in range(1, 5)]
    assert flagged(marked(pages)) == set()


@pytest.mark.parametrize("heading", ["Annexure 5", "B. PRE-QUALIFICATION CRITERIA (PQC)"])
def test_structural_headings_are_never_boilerplate(heading):
    pages = [[header(heading), Text(72, 300, "body")] for _ in range(4)]
    assert flagged(marked(pages)) == set()


def test_vocabulary_running_title_is_stripped():
    # f2 pp71–78: "SPECIAL CONDITIONS OF CONTRACT" as an 11 pt bold running header.
    title = header("SPECIAL CONDITIONS OF CONTRACT", size=11, bold=True)
    pages = [[title, Text(72, 300, f"{i}. Clause text")] for i in range(1, 5)]
    assert {page for page, _ in flagged(marked(pages))} == {1, 2, 3, 4}


def test_page_number_lines_are_boilerplate_even_once():
    pages = [
        [
            Text(72, 300, "body"),
            header("SOR Page 3 of 10"),
            footer("Sys. Gen.", y=795),
            footer("Tender: T1 Page 1 of 1"),
        ]
    ]
    assert flagged(marked(pages)) == {
        (1, "SOR Page 3 of 10"),
        (1, "Sys. Gen."),
        (1, "Tender: T1 Page 1 of 1"),
    }


def test_spacing_variants_of_a_running_header_are_one_group():
    # f1 pp41–42 read "NRL Tender No. : PUR…" where 23 other pages read "NRL Tender No.: PUR…".
    pages = [[header("NRL Tender No.: PUR1"), Text(72, 300, "body")] for _ in range(3)]
    pages += [[header("NRL Tender No. : PUR1"), Text(72, 300, "body")] for _ in range(2)]
    assert {page for page, _ in flagged(marked(pages))} == {1, 2, 3, 4, 5}


def test_repeated_text_outside_the_bands_is_kept():
    pages = [[Text(72, 420, "Signature of bidder with seal")] for _ in range(5)]
    assert flagged(marked(pages)) == set()


def test_first_content_line_is_found_after_stripping():
    # f1 p16: "Annexure 1" is first only once the Job Name / Tender No. lines are gone.
    page = [
        header("Job Name : Supply of FLP lights"),
        header("NRL Tender No.: PUR1", y=58),
        Text(72, 130, "Annexure 1", size=12, bold=True),
        Text(72, 300, "body"),
    ]
    doc = marked([page, page, page])
    assert [first_content_line(doc, p) for p in (1, 2, 3)] == ["Annexure 1"] * 3


def test_groups_record_the_first_occurrence():
    pages = [[Text(72, 300, "cover")]]
    pages += [[header("Technical Tender Document"), Text(72, 300, "spec")] for _ in range(4)]
    (group,) = marked(pages).boilerplate_groups
    assert (group.band, group.text, group.pages, group.first_page) == (
        "top",
        "Technical Tender Document",
        [2, 3, 4, 5],
        2,
    )


# Text layer, decided after boilerplate -----------------------------------------------------------

FOOTER = "Tender: T1 Page {} of 4 Sys. Gen."
RUNNING = "Running Header Of The Tender"


def test_footer_alone_is_not_a_text_layer():
    # f2 pp84–85: 42 chars of footer around a drawing.
    pages = [
        [
            header(RUNNING),
            Text(72, 300, "Real body text on this page of the tender"),
            footer(FOOTER.format(i)),
        ]
        for i in (1, 2, 3)
    ]
    pages.append([header(RUNNING), Image((100, 150, 500, 700)), footer(FOOTER.format(4))])
    raw = ingest(make_pdf(pages))
    assert sum(len(line.text) for line in raw.pages[3].lines) >= 20  # a naive check says "digital"

    doc = mark_boilerplate(raw)
    drawing = doc.pages[3]
    assert (drawing.has_text_layer, drawing.is_image_only, drawing.needs_ocr) == (
        False,
        True,
        False,
    )
    assert all(page.has_text_layer and not page.is_image_only for page in doc.pages[:3])
    assert [(warning.code, warning.page) for warning in doc.warnings] == [("PAGE_IMAGE_ONLY", 4)]


def test_image_only_page_needs_ocr_when_ocr_is_enabled():
    doc = marked(
        [[footer(FOOTER.format(1)), Image((100, 150, 500, 700))]], Settings(ocr={"enabled": True})
    )
    assert doc.pages[0].needs_ocr is True
    assert doc.warnings == []


def test_vector_drawing_counts_as_image_only():
    doc = marked([[footer(FOOTER.format(1)), Strokes(60)]])
    assert doc.pages[0].is_image_only is True


def test_blank_page_is_not_image_only():
    page = marked([[footer(FOOTER.format(1))]]).pages[0]
    assert (page.has_text_layer, page.is_image_only) == (False, False)


def test_body_font_size_ignores_boilerplate():
    running = header("A long running header line set in fourteen point type", size=14)
    raw = ingest(make_pdf([[running, Text(72, 300, "short body", size=9)] for _ in range(3)]))
    assert raw.pages[0].body_font_size == 14.0
    assert mark_boilerplate(raw).pages[0].body_font_size == 9.0


# Re-admission ------------------------------------------------------------------------------------


def vocabulary(text: str) -> str:
    return {"special conditions of contract": "scc"}.get(text.lower(), "other")


def running_scc_title() -> ParsedDocument:
    pages = [[Text(72, 300, "cover")]]
    pages += [
        [header("SPECIAL CONDITIONS OF CONTRACT"), Text(72, 300, f"clause {i}")] for i in range(3)
    ]
    return marked(pages)


def test_readmission_returns_the_first_occurrence_when_no_section_has_the_label():
    (line,) = lines_to_readmit(running_scc_title(), vocabulary, accepted_labels=set())
    assert (line.page, line.text, line.is_boilerplate) == (
        2,
        "SPECIAL CONDITIONS OF CONTRACT",
        False,
    )


def test_readmission_is_a_noop_when_a_section_carries_the_label():
    # f2: Annexure 20 carries scc, so the running header stays stripped.
    assert lines_to_readmit(running_scc_title(), vocabulary, accepted_labels={"scc"}) == []


# Fixtures (skipped until the PDFs are in tests/fixtures/) ------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_expected_boilerplate_is_flagged(name):
    texts = [text for _, text in flagged(marked_doc(name))]
    missing = [
        s for s in expected(name)["boilerplate_lines_expected"] if not any(s in t for t in texts)
    ]
    assert missing == []


def test_f1_annexure_3_is_never_boilerplate():
    lines = [
        line
        for page in marked_doc(F1).pages
        for line in page.lines
        if re.match(r"Annexure 3(?![.\d])", line.text)
    ]
    assert 24 in {line.page for line in lines}
    assert [line.page for line in lines if line.is_boilerplate] == []


# The first non-boilerplate line of the page: "first+3" in SPEC §5c, and first_on_page for the
# unlettered level-1 headings of f2 (SPEC §6).
FIRST_CONTENT_LINE = {
    F1: {
        5: "B. PRE-QUALIFICATION CRITERIA (PQC)",
        14: "D. TENDER ANNEXURES",
        16: "Annexure 1",
        17: "Information for transporter / goods carrier",
        41: "Annexure 14",
        42: "Annexure 14.1",
        52: "Annexure 18",
        59: "22 Acceptance of bid &",
    },
    F2: {
        2: "NOTICE INVITING TENDER",
        11: "PRE-QUALIFICATION CRITERIA (PQC)",
        14: "BID REJECTION CRITERIA",
        15: "AGREED TERMS & CONDITIONS (ATC)",
        17: "LIST OF ANNEXURES",
        58: "Annexure 19",
        59: "SCHEDULE OF RATES",
    },
}


@pytest.mark.parametrize(
    ("name", "page", "text"),
    [
        (name, page, text)
        for name, pages in FIRST_CONTENT_LINE.items()
        for page, text in pages.items()
    ],
)
def test_fixture_first_content_line(name, page, text):
    first = first_content_line(marked_doc(name), page)
    assert re.match(re.escape(text) + r"(?![\w.])", first), first


def test_f2_annexure_cover_titles_are_larger_than_the_body():
    # SPEC §5b emphasis: font_size >= body + 1.5. The covers' own font mode is the title's 36 pt.
    doc = marked_doc(F2)
    covers = {58: "SCHEDULE OF RATES", 69: "SPECIAL CONDTIONS OF", 79: "TECHNICAL SPECIFICATIONS"}
    for number, title in covers.items():
        page = doc.pages[number - 1]
        (line,) = [line for line in page.lines if line.text == title]
        assert line.font_size >= page.body_font_size + 1.5, (number, page.body_font_size)


def test_f2_image_only_pages():
    pages = marked_doc(F2).pages
    assert [page.number for page in pages if page.is_image_only] == expected(F2)["document"][
        "image_only_pages"
    ]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_needs_no_ocr(name):
    pages = marked_doc(name).pages
    assert [page.number for page in pages if page.needs_ocr] == expected(name)["document"][
        "needs_ocr_pages"
    ]
