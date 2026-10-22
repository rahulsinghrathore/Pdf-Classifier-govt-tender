"""Vocabulary: titles → canonical labels (SPEC §10)."""

from __future__ import annotations

import pytest

from tender_sections.config import Settings
from tender_sections.labels import OTHER, label_for, label_for_text, resolve_targets
from tender_sections.models import IndexEntry, Section, TargetSource

VOCABULARY = Settings().labels


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("NOTICE INVITING TENDER", "nit"),
        ("PRE-QUALIFICATION CRITERIA (PQC)", "pqc"),
        ("Pre-Qualifying Criteria (PQC)", "pqc"),  # f1 p2 contents: by the acronym
        ("BID REJECTION CRITERIA", "brc"),
        ("AGREED TERMS & CONDITIONS (ATC)", "atc"),
        ("AGREED TERMS AND CONDITIONS (ATC)", "atc"),
        ("SPECIAL CONDTIONS OF CONTRACT", "scc"),  # f2 p69, typo in the source
        ("Special Conditions of Contract (SCC)", "scc"),
        ("SCHEDULE OF RATES", "sor"),
        ("Schedule Of Rates (SOR)", "sor"),
        ("TECHNICAL SPECIFICATIONS", "tech_spec"),
        ("NUMALIGARH REFINERY LIMITED General Purchase Conditions (Indigenous)", "gcc"),
        ("NRL GPC (Indigenous) 2024", "gcc"),
        ("Instruction To Bidder", "itb"),
        ("Checklist for submission of Unpriced Bid", "checklist"),
        ("LIST OF ANNEXURES", "annexure_list"),
        ("TENDER ANNEXURES", "annexure_list"),
        ("Annexures", "annexure_list"),
        ("Instructions: Bank Guarantee (BG) Submission", "bank_guarantee"),
        ("Code Of Integrity In Public Procurement", "declarations"),
    ],
)
def test_vocabulary_maps_titles(text, label):
    assert label_for_text(text, VOCABULARY) == label


@pytest.mark.parametrize(
    "text",
    [
        # f2 p29: "special conditions" without "contract" or SCC is not the SCC.
        "SPECIAL CONDITIONS FOR MICRO AND SMALL ENTERPRISES (MSEs) BIDDERS :",
        "PART–I: UNPRICED BID",  # whole words: "unpriced bid" is not "price bid"
        "Technical Tender Document",  # technical, but no specification
        "ANNEXURES NOT APPLICABLE FOR THIS TENDER",  # "annexures" only as the whole title
        "UNIT RATE",  # acronyms only as whole upper-case words: no NIT here
        "Sorting of bids",
        "Deviation Statement",
    ],
)
def test_vocabulary_leaves_other_titles_alone(text):
    assert label_for_text(text, VOCABULARY) == OTHER


def test_the_first_matching_label_wins():
    text = "SPECIAL CONDITIONS OF CONTRACT INCLUDING SCHEDULE OF RATES"
    assert label_for_text(text, VOCABULARY) == "scc"


def test_label_falls_back_to_the_index_description():
    assert label_for(
        "To, Numaligarh Refinery Limited,", "Bid Security Declaration", VOCABULARY
    ) == ("declarations")
    assert label_for("", "Schedule Of Rates (SOR)", VOCABULARY) == "sor"
    assert label_for("SCHEDULE OF RATES", None, VOCABULARY) == "sor"


def test_vocabulary_comes_from_settings():
    custom = Settings(labels={"vocabulary": {"hse": ("health safety + environment",)}}).labels
    assert label_for_text("HEALTH, SAFETY & ENVIRONMENT", custom) == "hse"
    assert label_for_text("NOTICE INVITING TENDER", custom) == OTHER


def section(label: str, level: int, start: int, end: int) -> Section:
    return Section(
        id=f"{label}_{start}",
        display_id="",
        title="",
        label=label,
        level=level,
        start_page=start,
        end_page=end,
        end_page_exclusive=end,
        starts_mid_page=False,
        confidence=1.0,
        decided_by="rules",
        evidence="",
    )


def test_target_resolves_to_the_shallowest_section():
    # f2: Annexure 21 (level 2) wins over "2. Technical Specification:" inside it (level 3).
    sections = [section("tech_spec", 2, 79, 85), section("tech_spec", 3, 83, 83)]
    targets, status, _ = resolve_targets(sections, [], VOCABULARY)
    assert (targets["tech_spec"], status["tech_spec"]) == ([79, 85], "found")


def test_a_tie_goes_to_the_earliest_section():
    targets, _, sources = resolve_targets(
        [section("sor", 2, 70, 72), section("sor", 2, 58, 68)], [], VOCABULARY
    )
    assert (targets["sor"], sources["sor"]) == ([58, 68], TargetSource(section="sor_58"))


def test_every_target_is_reported_found_not_applicable_or_absent():
    # f1: SCC is listed under "Annexures Not Applicable for this Tender"; nothing lists a SOR here.
    na = IndexEntry(
        id_norm="annexure_20",
        display_id="Annexure 20",
        description="Special Conditions of Contract (SCC)",
        applicability="not_applicable",
        page=15,
    )
    targets, status, sources = resolve_targets([section("pqc", 1, 5, 6)], [na], VOCABULARY)
    assert targets == {"pqc": [5, 6], "atc": None, "scc": None, "sor": None, "tech_spec": None}
    assert status == {
        "pqc": "found",
        "atc": "absent",
        "scc": "not_applicable",
        "sor": "absent",
        "tech_spec": "absent",
    }
    # The UI's tooltip: "listed as Not Applicable on p15".
    assert (sources["scc"].index_entry, sources["sor"]) == (na, TargetSource())
