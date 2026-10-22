"""Stage 3: contents and annexure-list blocks (SPEC §5a)."""

from __future__ import annotations

from collections import Counter

import pytest

from helpers import F1, F2, FIXTURE_NAMES, expected, indexed_doc
from pdfgen import Rows, Text, make_pdf
from tender_sections.boilerplate import mark_boilerplate
from tender_sections.index_pages import mark_index_blocks
from tender_sections.ingest import ingest
from tender_sections.models import ParsedDocument


def indexed(pages) -> ParsedDocument:
    return mark_index_blocks(mark_boilerplate(ingest(make_pdf(pages))))


def annexures(numbers, description="Bidder details") -> list[tuple[str, str]]:
    return [(f"Annexure {n}", description) for n in numbers]


def applicability(doc: ParsedDocument) -> dict[str, str]:
    return {entry.display_id: entry.applicability for entry in doc.index_entries}


# Synthetic ---------------------------------------------------------------------------------------


def test_annexure_table_is_an_index_block_but_its_title_is_not():
    title = Text(72, 60, "LIST OF ANNEXURES", size=11, bold=True)
    doc = indexed(
        [[title, Rows(60, 80, [("Number", "Short Description"), *annexures(range(1, 7))])]]
    )
    (page,) = doc.pages
    assert page.is_index_page
    assert [entry.id_norm for entry in doc.index_entries] == [f"annexure_{n}" for n in range(1, 7)]
    assert set(applicability(doc).values()) == {"applicable"}
    flags = {line.text: line.in_index_block for line in page.lines}
    assert flags.pop("LIST OF ANNEXURES") is False
    assert all(flags.values())


def test_too_few_listed_ids_is_not_an_index():
    doc = indexed([[Rows(60, 80, annexures(range(1, 5)))]])
    assert not doc.pages[0].is_index_page and doc.index_entries == []


def test_contents_title_lowers_the_minimum_and_admits_bare_letters():
    # f1 p2: four rows "A Checklist…" … "D Tender Annexures" under "Contents:".
    rows = [("SN", "Section"), ("A", "Checklist"), ("B", "Pre-Qualifying Criteria (PQC)")]
    rows += [("C", "Agreed Terms & Conditions (ATC)"), ("D", "Tender Annexures")]
    doc = indexed([[Text(72, 60, "Contents:", size=12, bold=True), Rows(60, 80, rows)]])
    assert [entry.id_norm for entry in doc.index_entries] == ["sec_A", "sec_B", "sec_C", "sec_D"]
    assert doc.index_entries[1].description == "Pre-Qualifying Criteria (PQC)"


def test_serial_number_column_before_the_id_is_skipped():
    rows = [("Sl.", "Number", "Description")]
    rows += [(str(n), f"Annexure {n}", "Bidder details") for n in range(1, 6)]
    doc = indexed([[Rows(40, 80, rows, widths=(40, 120, 300))]])
    assert [e.id_norm for e in doc.index_entries] == [f"annexure_{n}" for n in range(1, 6)]
    assert {e.description for e in doc.index_entries} == {"Bidder details"}


def test_lettered_clause_table_without_a_contents_title_is_not_an_index():
    # f2 p15: the ATC table has rows A–Q but lists clauses, not sections.
    heading = Text(72, 60, "AGREED TERMS & CONDITIONS (ATC)", size=11, bold=True)
    rows = [
        (letter, "RATES: Rates should be quoted in line with the tender") for letter in "ABCDEF"
    ]
    doc = indexed([[heading, Rows(60, 80, rows)]])
    assert not doc.pages[0].is_index_page


def test_tables_of_long_descriptions_are_not_an_index():
    long = "Self-Declaration of Debarment / Blacklisting / Holiday listing and Allied Firms, " * 2
    rows = annexures(range(1, 7), description=long)
    doc = indexed([[Rows(30, 80, rows, widths=(100, 440), size=6)]])
    assert not doc.pages[0].is_index_page


def test_not_applicable_heading_governs_the_rest_of_the_page_and_the_next_page():
    page1 = [
        Text(72, 60, "LIST OF ANNEXURES", size=11, bold=True),
        Rows(60, 80, annexures(range(1, 6))),
        Text(150, 215, "Annexures Not Applicable for this Tender", size=12, bold=True),
        Rows(60, 230, annexures((6, 7))),
    ]
    page2 = [Rows(60, 60, annexures(range(8, 13)))]  # continues the not-applicable list
    page3 = [Text(72, 300, "an ordinary page of the tender")]
    page4 = [Rows(60, 60, annexures(range(13, 18)))]  # a new list: not governed
    status = applicability(indexed([page1, page2, page3, page4]))
    assert Counter(status.values()) == {"applicable": 10, "not_applicable": 7}
    assert [status[f"Annexure {n}"] for n in (5, 6, 12, 13)] == [
        "applicable",
        "not_applicable",
        "not_applicable",
        "applicable",
    ]


def test_empty_or_placeholder_descriptions_are_external():
    rows = [("Annexure 1", "Bidder details"), ("Annexure 2", "None"), ("Annexure 3", "-")]
    rows += [
        ("Annexure 4", "GPC available at website"),
        ("Annexure 5", ""),
        ("Annexure 6", "Format"),
    ]
    doc = indexed([[Rows(60, 80, rows)]])
    status = applicability(doc)
    assert [status[f"Annexure {n}"] for n in range(1, 7)] == [
        "applicable",
        "external",
        "external",
        "external",
        "external",
        "applicable",
    ]
    assert doc.index_entries[1].description is None


def test_unruled_list_of_short_id_lines_is_found_by_the_line_route():
    lines = [Text(72, 100 + 18 * i, f"Annexure {i + 1} Format: Declaration") for i in range(6)]
    doc = indexed([[Text(72, 70, "LIST OF ANNEXURES", bold=True), *lines]])
    assert doc.pages[0].is_index_page
    assert [entry.description for entry in doc.index_entries] == ["Format: Declaration"] * 6


# Fixtures (skipped until the PDFs are in tests/fixtures/) ------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_index_pages(name):
    pages = indexed_doc(name).pages
    assert [page.number for page in pages if page.is_index_page] == expected(name)["index_pages"]


@pytest.mark.parametrize(
    ("name", "counts", "external"),
    [
        (F1, {"applicable": 26, "not_applicable": 22}, []),
        (F2, {"applicable": 31, "not_applicable": 19, "external": 1}, ["17"]),
    ],
)
def test_fixture_annexure_applicability(name, counts, external):
    entries = [e for e in indexed_doc(name).index_entries if e.id_norm.startswith("annexure_")]
    ids = {
        state: sorted(e.display_id.split()[1] for e in entries if e.applicability == state)
        for state in counts
    }
    assert {state: len(found) for state, found in ids.items()} == counts
    assert ids["not_applicable"] == sorted(expected(name)["not_applicable_annexure_ids"])
    assert ids.get("external", []) == external
    assert sorted(ids["applicable"] + external) == sorted(expected(name)["expected_annexure_ids"])


def test_f1_contents_lists_sections_a_to_d():
    entries = [e for e in indexed_doc(F1).index_entries if e.page == 2]
    assert [(e.id_norm, e.applicability) for e in entries] == [
        (f"sec_{letter}", "applicable") for letter in "ABCD"
    ]


@pytest.mark.parametrize(
    ("name", "page", "title", "row"),
    [
        (F1, 14, "D. TENDER ANNEXURES", "Annexure 1 Instructions to Bidders (ITB)"),
        (F2, 17, "LIST OF ANNEXURES", "Annexure 19 Schedule Of Rates (SOR)"),
    ],
)
def test_fixture_index_title_is_outside_the_block(name, page, title, row):
    flags = {line.text: line.in_index_block for line in indexed_doc(name).pages[page - 1].lines}
    assert (flags[title], flags[row]) == (False, True)
