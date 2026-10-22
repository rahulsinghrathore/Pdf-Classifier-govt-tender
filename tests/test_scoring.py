"""Stage 5: heading scores (SPEC §5c)."""

from __future__ import annotations

import pytest

from helpers import (
    F1,
    F2,
    FIXTURE_NAMES,
    KNOWN_EXCEPTIONS,
    anchor,
    candidates_like,
    expected,
    scored,
)
from pdfgen import Rows, Text, make_pdf, paragraph
from tender_sections.boilerplate import mark_boilerplate
from tender_sections.candidates import find_candidates
from tender_sections.config import Settings
from tender_sections.index_pages import mark_index_blocks
from tender_sections.ingest import ingest
from tender_sections.levels import assign_levels
from tender_sections.models import Candidate
from tender_sections.scoring import reject_undecided, score_candidates


def scored_pages(pages, settings: Settings | None = None) -> list[Candidate]:
    doc = mark_index_blocks(mark_boilerplate(ingest(make_pdf(pages), settings), settings), settings)
    return score_candidates(find_candidates(doc, settings), doc, settings)


def on_page(found: list[Candidate], page: int) -> Candidate:
    return next(c for c in found if c.line.page == page)


SOR_COVER = [
    Text(72, 100, "Annexure 19", size=14, bold=True),
    Text(72, 300, "SCHEDULE OF RATES", size=36, bold=True),
]


# Synthetic ---------------------------------------------------------------------------------------


def test_repeated_title_without_a_new_id_is_penalized():
    # f2 p59: "SCHEDULE OF RATES" on the page after Annexure 19 began.
    sor_page = [Text(72, 100, "SCHEDULE OF RATES", size=24, bold=True), *paragraph(140)]
    found = scored_pages([SOR_COVER, sor_page, paragraph(100)])
    assert on_page(found, 1).decision == "accept"
    repeat = on_page(found, 2)
    # 9 - 5 = 4: back into the LLM's band, as f2 p59 in SPEC §5c.
    assert (repeat.score_breakdown.get("repeat_title"), repeat.score) == (-5, 4)


def test_new_annexure_with_the_same_label_is_not_a_repeat():
    # f1 Annexures 8, 9, 10 are all declarations, on consecutive pages.
    pages = [
        [Text(72, 100, f"Annexure {n} Self-Declaration of item {n}", bold=True), *paragraph(140)]
        for n in (8, 9, 10)
    ]
    found = scored_pages(pages)
    assert [(c.label, c.decision) for c in found] == [("declarations", "accept")] * 3


def test_repeat_window_is_limited():
    later = [Text(72, 100, "SCHEDULE OF RATES", size=24, bold=True), *paragraph(140)]
    found = scored_pages([SOR_COVER, paragraph(100), paragraph(100), paragraph(100), later])
    assert "repeat_title" not in on_page(found, 5).score_breakdown


def test_letter_already_used_at_level_1_is_penalized():
    # f1 p25 "D. Benefits Under …" after "D. TENDER ANNEXURES".
    pages = [
        [Text(72, 100, "D. TENDER ANNEXURES", size=12, bold=True), *paragraph(140)],
        [Text(72, 100, "D. Benefits Under The Policy", size=12, bold=True), *paragraph(140)],
    ]
    reuse = on_page(scored_pages(pages), 2)
    assert (reuse.score_breakdown.get("letter_reuse"), reuse.score) == (-4, 4)  # 8 - 4


def test_letter_missing_from_a_lettered_contents_is_penalized():
    # f1 p27 "F. Applicability of the Policy": the contents (p2) list A–D only.
    contents = [
        Text(72, 60, "Contents:", size=12, bold=True),
        Rows(60, 80, [("A", "Checklist"), ("B", "PQC"), ("C", "ATC"), ("D", "Tender Annexures")]),
    ]
    heading = [Text(72, 100, "F. Applicability of the Policy", size=12, bold=True), *paragraph(140)]
    unlisted = on_page(scored_pages([contents, heading]), 2)
    assert (unlisted.score_breakdown.get("unlisted_letter"), unlisted.decision) == (-5, "reject")
    # Without a lettered contents there is nothing to be missing from.
    assert (
        "unlisted_letter" not in on_page(scored_pages([paragraph(100), heading]), 2).score_breakdown
    )


def test_undecided_band_is_rejected_without_the_llm():
    page = [
        Text(72, 100, "Information for transporter / goods carrier", size=12, bold=True),
        *paragraph(140),
    ]
    (candidate,) = scored_pages([page])
    assert (candidate.score, candidate.decision, candidate.decided_by) == (6, "undecided", None)
    (resolved,), warnings = reject_undecided([candidate])
    assert (resolved.decision, resolved.decided_by) == ("reject", "disabled")
    assert [(w.code, w.message.endswith("[1]")) for w in warnings] == [
        ("UNDECIDED_WITHOUT_LLM", True)
    ]


def test_numbered_clause_skips_the_llm_while_clauses_are_not_emitted():
    # Option A: "18. Schedule of Rates" (f2 p74) can never become a section, so no LLM call.
    page = [Text(72, 100, "18. Schedule of Rates", bold=True), *paragraph(140)]
    (clause,) = scored_pages([page])
    assert (clause.score, clause.decision, clause.decided_by) == (7, "reject", "rules")
    assert clause.score_breakdown["not_emitted"] == 0
    (emitted,) = scored_pages([page], Settings(levels={"emit_numeric_clauses": True}))
    assert (emitted.score, emitted.decision) == (7, "undecided")


# Fixtures (skipped until the PDFs are in tests/fixtures/) ------------------------------------------

# The LLM's band: every 4–7 candidate that could change the result (SPEC §5c).
LLM_BAND_PAGES = {F1: [17], F2: [1, 29, 31, 32, 70, 80]}


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_llm_band(name):
    pages = sorted({c.line.page for c in scored(name) if c.decision == "undecided"})
    assert pages == LLM_BAND_PAGES[name]


def trap_params(kind: str) -> list:
    return [
        pytest.param(name, item, id=f"{name[-4:]}-p{item['page']}-{item['text'][:24]}")
        for name in FIXTURE_NAMES
        for item in expected(name)["traps"][kind]
    ]


@pytest.mark.parametrize(("name", "item"), trap_params("must_accept"))
def test_must_accept_headings_score_at_least_8(name, item):
    hits = [
        c
        for c in candidates_like(scored(name), item["page"], item["text"])
        if c.line.text.startswith(item["text"])
    ]
    assert hits, "no candidate"
    best = max(hits, key=lambda c: c.score)
    assert best.score >= 8, best.score_breakdown
    if "title" in item:
        assert best.title == item["title"]


@pytest.mark.parametrize(("name", "item"), trap_params("must_reject_or_demote"))
def test_traps_score_at_most_7(name, item):
    key = anchor(name, item["page"], item["text"])
    assert key, "trap text is not on its page: the check below would pass on nothing"
    hits = candidates_like(scored(name), item["page"], key, item.get("y_hint"))
    assert all(c.score <= 7 for c in hits), [(c.score, c.score_breakdown) for c in hits]


# The safety net: a trap the LLM wrongly accepts must still be harmless, a sub-heading (level 3+),
# never a top-level section or an annexure. Only "unsure" traps (4–7) reach the LLM; the rules
# reject the rest. The one deliberate exception is in helpers.KNOWN_EXCEPTIONS.


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_traps_the_llm_sees_stay_harmless_if_accepted(name):
    candidates = list(scored(name))
    unsure = []
    for item in expected(name)["traps"]["must_reject_or_demote"]:
        key = anchor(name, item["page"], item["text"])
        hits = candidates_like(candidates, item["page"], key, item.get("y_hint")) if key else []
        unsure += [c for c in hits if c.decision == "undecided"]
    assert unsure, "no trap reaches the LLM: the check below would pass on nothing"
    harmful = set()
    for trap in unsure:
        forced = [
            c.model_copy(update={"decision": "accept"}) if c is trap else c for c in candidates
        ]
        (accepted,) = [c for c in assign_levels(forced) if c.line == trap.line]
        if accepted.level is None or accepted.level < 3:
            harmful.add((name, trap.line.page))
    assert harmful == {exception for exception in KNOWN_EXCEPTIONS if exception[0] == name}


# SPEC §5c worked examples: (fixture, page, line text, y hint, score).
WORKED_EXAMPLES = [
    (F1, 5, "B. PRE-QUALIFICATION CRITERIA (PQC)", None, 10),
    (F1, 14, "D. TENDER ANNEXURES", None, 10),
    (F1, 14, "Annexure 1 Instructions to Bidders", None, 0),
    (F1, 3, "Annexure 8", None, 2),
    (F1, 16, "Annexure 1", None, 10),
    (F1, 17, "Information for transporter / goods carrier", None, 6),
    (F1, 25, "D. Benefits Under The Public Procurement", None, 0),
    (F1, 52, "Annexure 18", None, 10),
    (F2, 2, "NOTICE INVITING TENDER", None, 9),
    (F2, 11, "PRE-QUALIFICATION CRITERIA (PQC)", 0.12, 9),
    (F2, 11, "PRE-QUALIFICATION CRITERIA (PQC)", 0.19, 2),
    (F2, 1, "PART–I: UNPRICED BID", None, 6),
    (F2, 17, "LIST OF ANNEXURES", None, 9),
    (F2, 58, "Annexure 19", None, 10),
    (F2, 70, "Special Conditions of Contract", None, 1),
    (F2, 74, "18. Schedule of Rates", None, 4),
    (F2, 83, "2. Technical Specification:", None, 5),
]


@pytest.mark.parametrize(
    ("name", "page", "text", "y_hint", "score"),
    [
        pytest.param(*example, id=f"{example[0][-4:]}-p{example[1]}-{example[4]}")
        for example in WORKED_EXAMPLES
    ],
)
def test_spec_worked_examples(name, page, text, y_hint, score):
    (candidate, *_) = candidates_like(scored(name), page, text, y_hint)
    assert candidate.score == score, candidate.score_breakdown


@pytest.mark.parametrize(
    ("name", "page", "text"),
    [
        # Scored 2 in SPEC §5c. The clause title shares a baseline with its body cell, so the line
        # is "22 Acceptance of bid & Upon acceptance of bid, a brief LOA …": not bold, too long.
        (F1, 59, "22 Acceptance of bid &"),
        # Scored 4. Not first on its page and no vocabulary label, so no §5b kind applies.
        (F2, 29, "SPECIAL CONDITIONS FOR MICRO AND SMALL ENTERPRISES"),
        # Scored 4. It is the title row of a ruled table on p59, so the −5 applies as well.
        (F2, 59, "SCHEDULE OF RATES"),
    ],
)
def test_spec_examples_scored_differently_are_still_rejected(name, page, text):
    assert all(c.decision == "reject" for c in candidates_like(scored(name), page, text))


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_rules_alone_accept_exactly_the_expected_sections(name):
    accepted = [c for c in scored(name) if c.decision == "accept"]
    keys = sorted(c.id_norm if c.kind == "named" else c.label for c in accepted)
    assert keys == sorted(expected(name)["flat_inclusive"])
