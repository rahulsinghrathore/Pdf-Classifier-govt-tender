"""Stage 9: document-level checks (SPEC §9)."""

from __future__ import annotations

from synthetic import heading
from tender_sections.assemble import assemble
from tender_sections.models import Bookmark, Candidate, IndexEntry, ParsedDocument
from tender_sections.validate import Validation, validate

PQC = heading(5, "letter", id="B", title="PRE-QUALIFICATION CRITERIA", label="pqc", level=1)
ANNEXURES = heading(14, "letter", id="D", title="TENDER ANNEXURES", label="annexure_list", level=1)


def run(
    headings: list[Candidate],
    *,
    page_count: int = 20,
    entries: tuple[IndexEntry, ...] = (),
    bookmarks: tuple[Bookmark, ...] = (),
) -> Validation:
    doc = ParsedDocument(
        page_count=page_count, pages=[], index_entries=list(entries), bookmarks=list(bookmarks)
    )
    return validate(assemble(headings, page_count), doc)


def entry(number: str, description: str | None, applicability: str = "applicable") -> IndexEntry:
    return IndexEntry(
        id_norm=f"annexure_{number.replace('.', '_')}",
        display_id=f"Annexure {number}",
        description=description,
        applicability=applicability,
        page=14,
    )


def codes(result: Validation) -> list[str]:
    return [warning.code for warning in result.warnings]


def test_clean_document_has_no_warnings():
    headings = [PQC, ANNEXURES, heading(16, id="1", level=2)]
    result = run(headings, page_count=20, entries=(entry("1", "Instructions to Bidders"),))
    assert (codes(result), result.triggers) == ([], [])


def test_no_sections():
    assert run([]).triggers == ["NO_SECTIONS"]


def test_letters_and_annexures_must_run_in_order():
    a = heading(7, "letter", id="A", title="CHECKLIST", label="checklist", level=1)
    assert run([PQC, a]).triggers == ["ORDER_VIOLATION"]
    swapped = [ANNEXURES, heading(15, id="3", level=2), heading(17, id="2.6", level=3)]
    assert run(swapped).triggers == ["ORDER_VIOLATION"]


def test_each_id_family_numbers_on_its_own():
    form = heading(16, id="1", id_norm="form_1", display_id="Form 1", level=2)
    in_order = [ANNEXURES, heading(15, id="5", level=2), form, heading(17, id="6", level=2)]
    assert "ORDER_VIOLATION" not in codes(run(in_order))


def test_target_listed_as_applicable_but_missing():
    result = run([PQC, ANNEXURES], entries=(entry("19", "Schedule Of Rates (SOR)"),))
    assert "TARGET_LISTED_BUT_MISSING" in result.triggers


def test_one_missing_listed_id_is_a_warning_two_fail_the_document():
    # f2 Annexure 17: listed with no description, absent from the body. A warning only.
    one = run([PQC, ANNEXURES], entries=(entry("17", None, "external"),))
    assert (codes(one), one.triggers, one.expected_but_missing) == (
        ["EXPECTED_MISSING"],
        [],
        ["annexure_17"],
    )
    two = run([PQC, ANNEXURES], entries=(entry("17", None, "external"), entry("8", "Format")))
    assert two.triggers == ["EXPECTED_MISSING"]


def test_not_applicable_annexure_found():
    result = run(
        [ANNEXURES, heading(16, id="20", level=2)], entries=(entry("20", "SCC", "not_applicable"),)
    )
    assert (result.triggers, result.not_applicable_found) == (
        ["NOT_APPLICABLE_FOUND"],
        ["annexure_20"],
    )


def test_suspicious_lengths():
    # A level-2 section over 40% of the document.
    long = run([ANNEXURES, heading(15, id="1", level=2)], page_count=30)
    assert long.triggers == ["SUSPICIOUS_LENGTH"]
    # A level-1 section sharing its only page with the next one.
    atc = heading(
        5, "letter", id="C", title="AGREED TERMS", label="atc", level=1, first=False, y=0.6
    )
    assert run([PQC, atc]).triggers == ["SUSPICIOUS_LENGTH"]


def test_unassigned_pages_inside_the_document_are_a_warning():
    # Level-1 ranges are contiguous by construction, so only a prefix (cover, contents) or a
    # suffix is ever unassigned; the check guards that invariant. Set a gap by hand.
    assembly = assemble(
        [heading(1, "letter", id="A", title="CHECKLIST", label="checklist", level=1)], 6
    )
    doc = ParsedDocument(page_count=6, pages=[])
    assembly.unassigned_pages = [3, 4]
    assert codes(validate(assembly, doc)) == ["UNASSIGNED_INTERIOR"]
    assembly.unassigned_pages = [1, 2, 6]
    assert codes(validate(assembly, doc)) == []


def test_bookmark_without_a_heading_is_a_warning():
    result = run([PQC], bookmarks=(Bookmark(level=1, title="Technical", page=9),))
    assert (codes(result), result.triggers) == (["BOOKMARK_MISMATCH"], [])
