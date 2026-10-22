"""Stage 7: the LLM judges the undecided band (SPEC §7). Fake client only: no network."""

from __future__ import annotations

import pytest

from fakes import shown, verdict
from helpers import FIXTURE_NAMES, KNOWN_EXCEPTIONS, anchor, expected, fixture_pdf
from pdfgen import Text, make_pdf, paragraph
from tender_sections import extract
from tender_sections.boilerplate import mark_boilerplate
from tender_sections.candidates import find_candidates
from tender_sections.config import Settings
from tender_sections.index_pages import mark_index_blocks
from tender_sections.ingest import ingest
from tender_sections.llm import AnthropicClient, FakeLLMClient, LLMError, adjudicate
from tender_sections.llm.prompts import ADJUDICATE_SCHEMA
from tender_sections.models import Candidate, ParsedDocument
from tender_sections.scoring import score_candidates

NIT = [Text(72, 100, "NOTICE INVITING TENDER", bold=True), *paragraph(140)]
UNSURE = [Text(72, 100, "Information for transporter / goods carrier", size=12, bold=True)]
UNSURE += paragraph(140)  # score 6: a bold first line that names nothing


def scored_doc(pages) -> tuple[ParsedDocument, list[Candidate]]:
    doc = mark_index_blocks(mark_boilerplate(ingest(make_pdf(pages))))
    return doc, score_candidates(find_candidates(doc), doc)


def by_text(candidates: list[Candidate], start: str) -> Candidate:
    return next(c for c in candidates if c.line.text.startswith(start))


# Synthetic ---------------------------------------------------------------------------------------


def test_an_accepted_candidate_takes_the_verdict_and_a_capped_confidence():
    doc, candidates = scored_doc([NIT, UNSURE])
    result = adjudicate(candidates, doc, FakeLLMClient(verdict("accept", confidence=0.97)))
    unsure = by_text(result.candidates, "Information for transporter")
    assert (unsure.decision, unsure.decided_by, unsure.confidence) == ("accept", "llm", 0.85)
    assert unsure.evidence == "Information for transporter / goods carrier"
    assert (result.usage.candidate_calls, result.warnings) == (1, [])


def test_the_llm_sees_page_digests_never_the_pdf():
    doc, candidates = scored_doc([NIT, UNSURE])
    fake = FakeLLMClient(verdict("reject"))
    adjudicate(candidates, doc, fake)
    (request,) = fake.requests
    assert (request["schema"], request["effort"]) == (ADJUDICATE_SCHEMA, "low")
    assert "PART–I: UNPRICED BID" in request["system"]  # cover labels are not sections
    user = request["user"]
    assert user.startswith("Candidate 1\n<<PAGE 2>>")
    assert 'Previous accepted heading: "NOTICE INVITING TENDER" (level 1, page 1)' in user
    assert shown(request) == ["Information for transporter / goods carrier"]
    assert "first on page" in user and "score 6/10" in user


def test_evidence_that_is_not_on_the_page_is_discarded():
    # The model must not "find" Annexure 17 because the index mentions it.
    doc, candidates = scored_doc([NIT, UNSURE])
    fake = FakeLLMClient(verdict("accept", evidence="Annexure 17 General Information"))
    result = adjudicate(candidates, doc, fake)
    unsure = by_text(result.candidates, "Information for transporter")
    assert (unsure.decision, unsure.decided_by) == ("reject", "llm")
    assert [(w.code, w.page) for w in result.warnings] == [("LLM_EVIDENCE_MISMATCH", 2)]


def test_an_invalid_answer_is_retried_once_then_rejected():
    doc, candidates = scored_doc([NIT, UNSURE])
    fake = FakeLLMClient(lambda request: {"decisions": []})
    result = adjudicate(candidates, doc, fake)
    assert len(fake.requests) == 2
    assert "Your previous answer was not valid" in fake.requests[1]["user"]
    unsure = by_text(result.candidates, "Information for transporter")
    assert (unsure.decision, unsure.decided_by) == ("reject", "disabled")
    assert [w.code for w in result.warnings] == ["LLM_PARSE_FAILED"]


def test_a_corrected_second_answer_is_used():
    doc, candidates = scored_doc([NIT, UNSURE])
    answers = [lambda request: {"decisions": [{"candidate": 7}]}, verdict("accept")]
    fake = FakeLLMClient(lambda request: answers.pop(0)(request))
    result = adjudicate(candidates, doc, fake)
    assert by_text(result.candidates, "Information for transporter").decision == "accept"
    assert (result.usage.candidate_calls, result.warnings) == (2, [])


def test_an_unavailable_llm_rejects_the_band():
    def unavailable(request):
        raise LLMError("APIConnectionError: the network is down")

    doc, candidates = scored_doc([NIT, UNSURE])
    fake = FakeLLMClient(unavailable)
    result = adjudicate(candidates, doc, fake)
    unsure = by_text(result.candidates, "Information for transporter")
    assert (unsure.decision, unsure.decided_by, len(fake.requests)) == ("reject", "disabled", 1)
    assert [w.code for w in result.warnings] == ["LLM_UNAVAILABLE"]


def test_a_large_band_is_split_into_batches():
    other = [Text(72, 100, "Guidance for the carrier", size=12, bold=True), *paragraph(140)]
    doc, candidates = scored_doc([NIT, UNSURE, other])
    fake = FakeLLMClient(verdict("reject"))
    adjudicate(candidates, doc, fake, Settings(llm={"max_candidates_per_call": 1}))
    assert [len(shown(request)) for request in fake.requests] == [1, 1]


def test_no_undecided_candidate_means_no_call():
    doc, candidates = scored_doc([NIT])
    fake = FakeLLMClient(verdict("accept"))
    assert adjudicate(candidates, doc, fake).candidates == candidates
    assert fake.requests == []


def test_extract_uses_the_verdicts_and_reports_usage():
    pdf = make_pdf([NIT, UNSURE])
    accepted = extract(pdf, llm=FakeLLMClient(verdict("accept")))
    assert accepted.flat_inclusive == {"nit": [1, 2], "p2_heading": [2, 2]}
    assert accepted.llm_usage.candidate_calls == 1
    assert "UNDECIDED_WITHOUT_LLM" not in [w.code for w in accepted.warnings]
    rejected = extract(pdf, llm=FakeLLMClient(verdict("reject")))
    assert rejected.flat_inclusive == {"nit": [1, 2]}


def test_tests_cannot_build_the_real_client():
    with pytest.raises(AssertionError, match="FakeLLMClient"):
        AnthropicClient(Settings().llm)


# Fixtures (skipped until the PDFs are in tests/fixtures/) ------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_ground_truth_when_the_llm_rejects_the_band(name):
    fake = FakeLLMClient(verdict("reject"))
    result = extract(fixture_pdf(name), llm=fake)
    assert result.flat_inclusive == expected(name)["flat_inclusive"]
    assert result.flat_exclusive == expected(name)["flat_exclusive"]
    assert result.needs_human_review is False
    assert [r["schema"] for r in fake.requests] == [ADJUDICATE_SCHEMA]  # one batch, no fallback


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_safety_net_through_the_fake_llm(name):
    # The fake wrongly accepts everything it is shown. Every trap among those lines must still be
    # a sub-heading (level 3+), except the deliberate exception (helpers.KNOWN_EXCEPTIONS).
    result = extract(fixture_pdf(name), llm=FakeLLMClient(verdict("accept")), debug=True)
    assert result.debug is not None
    judged = [c for c in result.debug.candidates if c.decided_by == "llm"]
    harmful = set()
    for item in expected(name)["traps"]["must_reject_or_demote"]:
        key = anchor(name, item["page"], item["text"])
        for c in judged:
            if key and c.line.page == item["page"] and key in c.line.text and (c.level or 0) < 3:
                harmful.add((name, item["page"]))
    assert harmful == {exception for exception in KNOWN_EXCEPTIONS if exception[0] == name}
