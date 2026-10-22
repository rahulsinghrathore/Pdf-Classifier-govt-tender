"""The one whole-document LLM pass when a stage-9 check fails (SPEC §9). Fake client only."""

from __future__ import annotations

from pdfgen import Text, make_pdf, paragraph
from tender_sections import extract
from tender_sections.assemble import assemble
from tender_sections.boilerplate import mark_boilerplate
from tender_sections.index_pages import mark_index_blocks
from tender_sections.ingest import ingest
from tender_sections.llm import FakeLLMClient, LLMError, whole_document_pass
from tender_sections.llm.prompts import WHOLE_DOC_SCHEMA

# Plain-text headings: nothing scores as a heading, so the document fails with NO_SECTIONS.
PLAIN = make_pdf(
    [
        [Text(72, 100, "Notice inviting tender"), *paragraph(140)],
        paragraph(100),
        [Text(72, 100, "Pre-qualification criteria"), *paragraph(140)],
    ]
)


def section(page: int, title: str, level: int = 1, evidence: str | None = None) -> dict:
    return {"page": page, "id": "", "title": title, "level": level, "evidence": evidence or title}


def rebuild(request: dict) -> dict:
    assert request["schema"] is WHOLE_DOC_SCHEMA, "only the fallback should be asked"
    return {
        "sections": [section(1, "Notice inviting tender"), section(3, "Pre-qualification criteria")]
    }


def codes(result) -> list[str]:
    return [warning.code for warning in result.warnings]


def test_the_fallback_rebuilds_a_document_the_checks_failed():
    fake = FakeLLMClient(rebuild)
    result = extract(PLAIN, llm=fake)
    assert result.flat_inclusive == {"nit": [1, 2], "pqc": [3, 3]}
    assert (result.needs_human_review, result.llm_usage.whole_doc_pass) == (False, True)
    assert len(fake.requests) == 1


def test_the_request_names_the_failed_checks_and_marks_every_page():
    fake = FakeLLMClient(rebuild)
    extract(PLAIN, llm=fake)
    (request,) = fake.requests
    assert "NO_SECTIONS" in request["user"]
    assert all(f"<<PAGE {n}>>" in request["user"] for n in (1, 2, 3))
    assert request["effort"] == "medium"


def test_unverifiable_entries_are_dropped_and_the_document_flagged():
    # Annexure 17 is the kind of section a model invents from an index.
    invented = section(2, "General Information", 2, "Annexure 17 General Information")
    fake = FakeLLMClient(lambda request: {"sections": [invented]})
    result = extract(PLAIN, llm=fake)
    assert len(fake.requests) == 1  # one pass, never a loop
    assert result.needs_human_review is True
    assert {"LLM_EVIDENCE_MISMATCH", "NO_SECTIONS"} <= set(codes(result))


def test_an_unavailable_llm_leaves_the_document_for_review():
    def unavailable(request):
        raise LLMError("RateLimitError: retries exhausted")

    result = extract(PLAIN, llm=FakeLLMClient(unavailable))
    assert result.needs_human_review is True
    assert {"LLM_UNAVAILABLE", "NO_SECTIONS"} <= set(codes(result))


def test_a_heading_that_wraps_is_found_by_its_first_line():
    # f2 p69: Annexure 20's title "SPECIAL CONDTIONS OF" + "CONTRACT" spans two lines.
    page = [Text(72, 100, "Special conditions of"), Text(72, 114, "contract"), *paragraph(160)]
    doc = mark_index_blocks(mark_boilerplate(ingest(make_pdf([page]))))
    answer = {"sections": [section(1, "Special conditions of contract")]}
    result = whole_document_pass(doc, [], assemble([], 1), [], FakeLLMClient(lambda r: answer))
    (heading,) = result.headings
    assert (heading.line.text, heading.label, heading.level, heading.first_on_page) == (
        "Special conditions of",
        "scc",
        1,
        True,
    )
