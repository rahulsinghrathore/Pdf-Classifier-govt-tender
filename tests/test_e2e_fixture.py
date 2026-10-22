"""The contract: both fixtures reach their hand-verified ground truth with the LLM disabled."""

from __future__ import annotations

import pytest

from helpers import F1, F2, FIXTURE_NAMES, expected, indexed_doc, result, scored
from tender_sections.boilerplate import lines_to_readmit
from tender_sections.config import Settings
from tender_sections.labels import label_for_text
from tender_sections.models import Section

# The checks that would call the whole-document LLM pass (SPEC §9).
TRIGGERS = {
    "ORDER_VIOLATION",
    "TARGET_LISTED_BUT_MISSING",
    "NOT_APPLICABLE_FOUND",
    "SUSPICIOUS_LENGTH",
    "NO_SECTIONS",
}
UNDECIDED_PAGES = {F1: [17], F2: [1, 29, 31, 32, 70, 80]}


def without_comments(mapping: dict) -> dict:
    return {key: value for key, value in mapping.items() if not key.startswith("_")}


def walk(sections: list[Section]) -> list[Section]:
    return [s for section in sections for s in (section, *walk(section.children))]


pytestmark = pytest.mark.parametrize("name", FIXTURE_NAMES)


def test_targets(name):
    assert result(name).targets == without_comments(expected(name)["targets"])
    assert result(name).targets_status == expected(name)["targets_status"]


def test_flat_maps(name):
    assert result(name).flat_inclusive == expected(name)["flat_inclusive"]
    assert result(name).flat_exclusive == expected(name)["flat_exclusive"]


def test_levels(name):
    sections = walk(result(name).sections)
    by_key = {s.id: s.level for s in sections} | {
        s.display_id: s.level for s in sections if s.display_id
    }
    want = without_comments(expected(name)["tree_levels"])
    assert {key: by_key.get(key) for key in want} == want


def test_level1_titles(name):
    top = {s.id: s.evidence for s in result(name).sections if s.level == 1}
    assert top == expected(name)["level1_titles"]


def test_unassigned_pages_and_listed_ids(name):
    exp = expected(name)
    assert result(name).unassigned_pages == exp["unassigned_pages"]
    missing = [f"annexure_{n.replace('.', '_')}" for n in exp.get("expected_but_missing", [])]
    assert result(name).expected_but_missing == missing
    assert result(name).not_applicable_found == []


def test_the_fallback_does_not_fire(name):
    codes = [warning.code for warning in result(name).warnings]
    assert TRIGGERS.isdisjoint(codes)
    assert codes.count("EXPECTED_MISSING") < Settings().checks.expected_missing_trigger
    assert result(name).needs_human_review is False


def test_undecided_pages_without_the_llm(name):
    debug = result(name).debug
    assert debug is not None
    pages = sorted({c.line.page for c in debug.candidates if c.decided_by == "disabled"})
    assert pages == UNDECIDED_PAGES[name]
    assert [w.code for w in result(name).warnings].count("UNDECIDED_WITHOUT_LLM") == 1


def test_document_info(name):
    info, exp = result(name).document, expected(name)["document"]
    assert (info.pages, info.printed_page_offset, info.has_bookmarks) == (
        exp["pages"],
        exp["printed_page_offset"],
        exp["has_bookmarks"],
    )
    assert info.image_only_pages == exp.get("image_only_pages", [])
    assert info.needs_ocr_pages == exp["needs_ocr_pages"]


def test_readmission_is_a_no_op(name):
    # f2's running "SPECIAL CONDITIONS OF CONTRACT" stays stripped: Annexure 20 carries scc.
    labels = Settings().labels
    accepted = {c.label for c in scored(name) if c.decision == "accept"}
    assert lines_to_readmit(indexed_doc(name), lambda t: label_for_text(t, labels), accepted) == []
