"""Stage 8: the section tree and its page ranges (SPEC §8)."""

from __future__ import annotations

import pytest

from synthetic import heading
from tender_sections.assemble import assemble
from tender_sections.models import Section


def tree(sections: list[Section]) -> list:
    return [(s.id, tree(s.children)) if s.children else s.id for s in sections]


def test_nested_ranges_inclusive_and_exclusive():
    headings = [
        heading(1, "letter", id="A", title="CHECKLIST", label="checklist", level=1),
        heading(2, id="1", level=2),
        heading(4, id="2", level=2),
        heading(5, id="2.1", level=3),
    ]
    result = assemble(headings, page_count=8)
    assert result.flat_inclusive == {
        "checklist": [1, 8],
        "annexure_1": [2, 3],
        "annexure_2": [4, 8],
        "annexure_2_1": [5, 8],
    }
    # A parent stops before its first child; leaves are the same in both views.
    assert result.flat_exclusive == {
        "checklist": [1, 1],
        "annexure_1": [2, 3],
        "annexure_2": [4, 4],
        "annexure_2_1": [5, 8],
    }
    assert tree(result.sections) == [
        ("checklist", ["annexure_1", ("annexure_2", ["annexure_2_1"])])
    ]


def test_heading_that_starts_mid_page_shares_the_page():
    headings = [heading(2, id="1", level=2), heading(3, id="2", level=2, first=False, y=0.5)]
    result = assemble(headings, page_count=5)
    assert result.flat_inclusive == {"annexure_1": [2, 3], "annexure_2": [3, 5]}
    assert result.flat[1].starts_mid_page


def test_orphan_keeps_its_level_and_ends_the_previous_annexure():
    # f1: Annexure 6 (p29), 6.1 (p31), 7.2 (p32, no Annexure 7), 7.2.1 (p34), 8 (p35).
    headings = [
        heading(1, "letter", id="D", title="TENDER ANNEXURES", label="annexure_list", level=1),
        heading(2, id="6", level=2),
        heading(3, id="6.1", level=3),
        heading(4, id="7.2", level=3),
        heading(5, id="7.2.1", level=4),
        heading(6, id="8", level=2),
    ]
    result = assemble(headings, page_count=7)
    assert result.flat_inclusive == {
        "annexure_list": [1, 7],
        "annexure_6": [2, 3],
        "annexure_6_1": [3, 3],
        "annexure_7_2": [4, 5],
        "annexure_7_2_1": [5, 5],
        "annexure_8": [6, 7],
    }
    assert tree(result.sections) == [
        (
            "annexure_list",
            [("annexure_6", ["annexure_6_1"]), ("annexure_7_2", ["annexure_7_2_1"]), "annexure_8"],
        )
    ]


def test_two_headings_cannot_both_open_one_page():
    # Only one line can be first on a page; otherwise the first heading would end before it starts.
    both_first = [heading(2, id="1", level=2), heading(2, id="2", level=2, y=0.5)]
    with pytest.raises(AssertionError):
        assemble(both_first, page_count=4)


def test_unassigned_pages_are_outside_every_level_1_section():
    headings = [
        heading(3, "titled", title="NOTICE INVITING TENDER", label="nit", level=1),
        heading(6, "titled", title="BID REJECTION CRITERIA", label="brc", level=1),
    ]
    assert assemble(headings, page_count=8).unassigned_pages == [1, 2]


def test_keys_fall_back_to_ids_and_stay_unique():
    headings = [
        heading(1, "letter", id="B", title="GENERAL", level=1),  # no label: its id
        heading(2, "titled", title="PRE-QUALIFICATION CRITERIA", label="pqc", level=1),
        heading(3, "titled", title="PRE-QUALIFICATION CRITERIA", label="pqc", level=1),
        heading(4, "titled", title="Scope of Work", label="scope", level=3),
    ]
    assert list(assemble(headings, page_count=5).flat_inclusive) == [
        "sec_B",
        "pqc",
        "pqc_2",
        "p4_scope",
    ]


def test_headings_are_ordered_by_page_and_position():
    headings = [heading(4, id="2", level=2), heading(2, id="1", level=2)]
    assert list(assemble(headings, page_count=5).flat_inclusive) == ["annexure_1", "annexure_2"]


def test_section_fields():
    (section,) = assemble(
        [heading(19, id="1", title="Instructions To Bidders", label="itb", level=2, score=9)], 20
    ).flat
    assert (section.display_id, section.label, section.confidence, section.decided_by) == (
        "Annexure 1",
        "itb",
        0.9,
        "rules",
    )
    assert section.evidence == "Annexure 1 Instructions To Bidders"
