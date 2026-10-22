"""extract() on synthetic documents: the paths both fixtures leave unexercised."""

from __future__ import annotations

from pdfgen import Text, header, make_pdf, paragraph
from tender_sections import extract


def test_running_title_that_is_the_only_heading_is_readmitted():
    # SPEC §4 step 6: the SCC exists only as a running header, so its first occurrence returns.
    nit = [Text(72, 100, "NOTICE INVITING TENDER", bold=True), *paragraph(140)]
    scc = [
        [
            header("SPECIAL CONDITIONS OF CONTRACT", size=11, bold=True),
            Text(72, 100, f"{i}. Clause text", bold=True),
            *paragraph(140),
        ]
        for i in range(1, 5)
    ]
    result = extract(make_pdf([nit, *scc]), debug=True)
    assert result.flat_inclusive == {"nit": [1, 1], "scc": [2, 5]}
    assert (result.targets["scc"], result.targets_status["scc"]) == ([2, 5], "found")
    # The re-admitted title now opens p2; the clause below it no longer does.
    assert result.debug is not None
    first = [c.line.text for c in result.debug.candidates if c.line.page == 2 and c.first_on_page]
    assert first == ["SPECIAL CONDITIONS OF CONTRACT"]


def test_blank_document_asks_for_human_review():
    result = extract(make_pdf([[]]))
    assert (result.flat_inclusive, result.needs_human_review) == ({}, True)
    assert [warning.code for warning in result.warnings] == ["NO_SECTIONS"]
    assert set(result.targets_status.values()) == {"absent"}
