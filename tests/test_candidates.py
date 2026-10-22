"""Stage 4: heading candidates and bare-id titles (SPEC §5b)."""

from __future__ import annotations

import pytest

from helpers import F1, F2, expected, indexed_doc
from pdfgen import Rows, Text, make_pdf, paragraph
from tender_sections.boilerplate import mark_boilerplate
from tender_sections.candidates import find_candidates
from tender_sections.index_pages import mark_index_blocks
from tender_sections.ingest import ingest
from tender_sections.models import Candidate


def candidates(pages) -> list[Candidate]:
    doc = mark_index_blocks(mark_boilerplate(ingest(make_pdf(pages))))
    return find_candidates(doc)


def summary(found: list[Candidate]) -> list[tuple]:
    return [(c.kind, c.id_norm, c.title, c.label, c.first_on_page) for c in found]


def test_candidate_kinds():
    page1 = [
        Text(72, 100, "B. PRE-QUALIFICATION CRITERIA (PQC)", size=12, bold=True),
        Text(72, 140, "Annexure 2.6.1 Format: Exceptions And Deviations", bold=True),
        Text(72, 180, "18. Schedule of Rates", bold=True),
        Text(72, 220, "NOTICE INVITING TENDER", bold=True),
        *paragraph(260),
    ]
    page2 = [
        Text(72, 100, "Information for transporter / goods carrier", size=12, bold=True),
        *paragraph(140),
    ]
    assert summary(candidates([page1, page2])) == [
        ("letter", "sec_B", "PRE-QUALIFICATION CRITERIA (PQC)", "pqc", True),
        ("named", "annexure_2_6_1", "Format: Exceptions And Deviations", "other", False),
        ("numeric", "clause_18", "Schedule of Rates", "sor", False),
        ("titled", None, "NOTICE INVITING TENDER", "nit", False),
        ("layout_only", None, "Information for transporter / goods carrier", "other", True),
    ]


def test_list_items_captions_and_plain_vocabulary_words_are_not_candidates():
    page = [
        Text(72, 100, "Contents:", size=12, bold=True),  # f1 p2: names no section
        Text(72, 140, "d) Schedule of Rates / Price Schedule / Price Basis", bold=True),  # f2 p14
        Text(72, 180, "clause 7.2 of GCC)."),  # f2 p7: the end of a sentence
        *paragraph(220),
    ]
    assert candidates([page]) == []


def test_named_heading_must_start_the_line():
    page = [*paragraph(100), Text(72, 200, "as per Annexure 8 enclosed", bold=True)]
    assert candidates([page]) == []


def test_bare_id_takes_the_largest_emphasized_lines_below():
    # f2 p69: "SPECIAL CONDTIONS OF" + "CONTRACT", two 36 pt lines far below the 14 pt id.
    cover = [
        Text(72, 100, "Annexure 20", size=14, bold=True),
        Text(72, 300, "SPECIAL CONDTIONS OF", size=36),
        Text(72, 345, "CONTRACT", size=36),
        Text(72, 380, "Name of work", size=16, bold=True),
        Text(72, 600, "LOWER HALF", size=40),  # below the top half: ignored
    ]
    (annexure, *_) = candidates([cover, paragraph(100)])
    assert (annexure.title, annexure.title_source, annexure.label) == (
        "SPECIAL CONDTIONS OF CONTRACT",
        "lines_below",
        "scc",
    )


def test_salutation_is_not_a_title():
    page = [
        Text(72, 100, "Annexure 14.1", size=12, bold=True),
        Text(72, 140, "To, Numaligarh Refinery Limited,", size=12, bold=True),
        Text(72, 170, "Subject: Bid Security Declaration", size=11, bold=True),
        *paragraph(220),
    ]
    assert candidates([page])[0].title == "Subject: Bid Security Declaration"


def test_bare_id_falls_back_to_the_index_description():
    index = [
        Text(72, 60, "LIST OF ANNEXURES", size=11, bold=True),
        Rows(
            60,
            80,
            [
                (f"Annexure {n}", "Schedule Of Rates (SOR)" if n == 19 else "Format")
                for n in range(15, 21)
            ],
        ),
    ]
    body = [Text(72, 100, "Annexure 19", bold=True), *paragraph(140)]
    found = [c for c in candidates([index, body]) if c.line.page == 2]
    assert summary(found)[0] == ("named", "annexure_19", "Schedule Of Rates (SOR)", "sor", True)
    assert found[0].title_source == "index"


# Fixtures (skipped until the PDFs are in tests/fixtures/) ------------------------------------------


@pytest.mark.parametrize(
    ("id_norm", "title"),
    [(k, v) for k, v in expected(F2)["annexure_titles_from_body"].items() if not k.startswith("_")],
)
def test_f2_bare_annexure_titles_come_from_the_body(id_norm, title):
    found = [
        c for c in find_candidates(indexed_doc(F2)) if c.id_norm == id_norm and c.first_on_page
    ]
    assert [(c.title, c.title_source) for c in found] == [(title, "lines_below")]


def test_f1_annexure_18_title_and_label():
    # All three consecutive 12 pt lines below the id; SPEC §5b quotes the first two.
    (annexure,) = [
        c
        for c in find_candidates(indexed_doc(F1))
        if c.id_norm == "annexure_18" and c.line.page == 52
    ]
    assert annexure.title.startswith(
        "NUMALIGARH REFINERY LIMITED General Purchase Conditions (Indigenous)"
    )
    assert (annexure.title_source, annexure.label) == ("lines_below", "gcc")
