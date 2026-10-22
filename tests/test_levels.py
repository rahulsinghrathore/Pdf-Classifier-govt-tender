"""Stage 6: heading levels and emission (SPEC §6)."""

from __future__ import annotations

from synthetic import heading
from tender_sections.config import Settings
from tender_sections.levels import assign_levels, emitted
from tender_sections.models import Candidate


def levels(*candidates: Candidate, settings: Settings | None = None) -> list[int | None]:
    return [c.level for c in assign_levels(list(candidates), settings)]


def test_lettered_section_in_capitals_is_level_1():
    assert levels(heading(3, "letter", id="A", title="CHECKLIST FOR DOCUMENT SUBMISSION")) == [1]


def test_unlettered_title_with_a_level_1_label_on_top_of_its_page_is_level_1():
    # f2: "NOTICE INVITING TENDER" has no letter; its label makes it a top-level section.
    nit = heading(2, "titled", title="NOTICE INVITING TENDER", label="nit")
    mid_page = heading(3, "titled", title="SCHEDULE OF RATES", label="sor", first=False)
    other = heading(4, "titled", title="Code of Integrity", label="declarations")
    assert levels(nit, mid_page, other) == [1, 3, 3]


def test_titled_heading_inside_the_annexures_is_a_sub_heading():
    # f2 p59 "SCHEDULE OF RATES" is first on its page, but Annexure 19 is open.
    annexures = heading(17, "titled", title="LIST OF ANNEXURES", label="annexure_list")
    sor = heading(58, id="19", title="SCHEDULE OF RATES", label="sor")
    repeat = heading(59, "titled", title="SCHEDULE OF RATES", label="sor")
    assert levels(annexures, sor, repeat) == [1, 2, 3]


def test_named_levels_follow_the_dots():
    part = heading(1, id="I", id_norm="part_I", display_id="Part I", title="UNPRICED BID")
    found = levels(part, heading(2, id="3"), heading(3, id="3.2"), heading(4, id="2.6.1"))
    assert found == [1, 2, 3, 4]


def test_orphans_keep_their_nominal_level():
    # There is no Annexure 7 on either fixture: 7.2 and 7.2.1 stay at levels 3 and 4.
    assert levels(heading(32, id="7.2"), heading(34, id="7.2.1")) == [3, 4]


def test_numbered_clauses_are_three_plus_dots():
    assert levels(heading(5, "numeric", id="18"), heading(6, "numeric", id="20.1.1")) == [3, 5]


def test_sub_headings_sit_below_the_open_heading():
    annexure = heading(16, id="1", title="Instruction To Bidder")
    transport = heading(17, "layout_only", title="Information for transporter", size=12)
    smaller = heading(17, "layout_only", title="Vehicles", size=10, y=0.4)
    sibling = heading(17, "layout_only", title="Drivers", size=10, y=0.6)
    lettered = heading(18, "letter", id="E", title="Relaxation of Past Track Record")
    # Smaller by 2 pt: one deeper; same size: a sibling; a lettered sub-heading: under the annexure.
    assert levels(annexure, transport, smaller, sibling, lettered) == [2, 3, 4, 4, 3]


def test_bare_id_title_line_is_consumed():
    # f2 p58: the 36 pt "SCHEDULE OF RATES" is Annexure 19's title, not a section of its own.
    annexure = heading(58, id="19", title="SCHEDULE OF RATES", source="lines_below")
    title_line = heading(58, "titled", title="SCHEDULE OF RATES", label="sor", first=False, y=0.3)
    _, consumed = assign_levels([annexure, title_line])
    assert (consumed.decision, consumed.level) == ("reject", None)


def test_only_accepted_candidates_get_a_level():
    found = levels(heading(1, id="1", decision="reject"), heading(2, id="2", decision="undecided"))
    assert found == [None, None]


def test_emitted_drops_deep_headings_and_internal_clauses():
    candidates = assign_levels(
        [
            heading(1, id="2"),
            heading(2, "titled", title="Scope of Work", label="scope", first=False),
            heading(3, id="2.6.1.1"),  # level 5 > max_emit_level 4
            heading(4, "numeric", id="18"),
        ]
    )
    assert [c.level for c in candidates] == [2, 3, 5, 3]
    assert [c.line.page for c in emitted(candidates)] == [1, 2]
    with_clauses = Settings(levels={"emit_numeric_clauses": True})
    assert [c.line.page for c in emitted(candidates, with_clauses)] == [1, 2, 4]


def test_sibling_sub_headings_share_a_level():
    # f1 Annexure 3 (MSE policy): lettered sub-headings E., F., G. — siblings, not a staircase.
    subs = [
        heading(26 + i, "letter", id=letter, title="Relaxation of the Policy")
        for i, letter in enumerate("EFG")
    ]
    assert levels(heading(24, id="3"), *subs) == [2, 3, 3, 3]
