"""Fixture PDFs (tests skip while a PDF is absent) and their hand-verified ground truth."""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tender_sections import extract
from tender_sections.boilerplate import mark_boilerplate
from tender_sections.candidates import find_candidates
from tender_sections.config import Settings
from tender_sections.index_pages import mark_index_blocks
from tender_sections.ingest import ingest
from tender_sections.models import Candidate, ExtractionResult, ParsedDocument
from tender_sections.scoring import score_candidates

FIXTURES = Path(__file__).parent / "fixtures"
F1 = "nrl_pur1011567"  # supply tender, 67 pp, lettered A.–D. sections, SCC/SOR/Tech Specs N/A
F2 = "nrl_pur1011848"  # works tender, 85 pp, unlettered sections, image-only pp84–85
FIXTURE_NAMES = (F1, F2)

# The trap safety net's one deliberate exception: f2 p1 "PART–I: UNPRICED BID" is a cover label,
# and a Part heading is level 1 by rule (SPEC §6). Only the LLM rejecting it protects it.
KNOWN_EXCEPTIONS = {(F2, 1)}


@cache
def expected(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))


def fixture_pdf(name: str) -> Path:
    path = FIXTURES / f"{name}.pdf"
    if not path.is_file():
        pytest.skip(f"fixture PDF not present: tests/fixtures/{path.name}")
    return path


@cache
def raw_doc(name: str) -> ParsedDocument:
    """Stage 1 output for a fixture, cached for the session. Do not mutate."""
    return ingest(fixture_pdf(name))


@cache
def marked_doc(name: str) -> ParsedDocument:
    """Stages 1–2 output for a fixture, cached for the session. Do not mutate."""
    return mark_boilerplate(raw_doc(name))


@cache
def indexed_doc(name: str) -> ParsedDocument:
    """Stages 1–3 output for a fixture, cached for the session. Do not mutate."""
    return mark_index_blocks(marked_doc(name))


@cache
def scored(name: str) -> tuple[Candidate, ...]:
    """Stage 5 output (scored candidates, no LLM) for a fixture, cached for the session."""
    doc = indexed_doc(name)
    return tuple(score_candidates(find_candidates(doc), doc))


def candidates_like(
    candidates: tuple[Candidate, ...] | list[Candidate],
    page: int,
    text: str,
    y_hint: float | None = None,
) -> list[Candidate]:
    """Candidates on the page whose line contains the text's first four words.

    Contains rather than equals: a table cell can merge with its neighbours on one baseline
    (f1 p59 "22 Acceptance of bid & Upon acceptance of bid, …").
    """
    key = re.compile(r"(?<!\S)" + re.escape(" ".join(text.split()[:4])) + r"(?!\S)")
    hits = [c for c in candidates if c.line.page == page and key.search(c.line.text)]
    if y_hint is not None and hits:
        hits = [min(hits, key=lambda c: abs(c.line.y0 - y_hint))]
    return hits


@cache
def result(name: str) -> ExtractionResult:
    """extract() on a fixture with the LLM off — the contract — debug included."""
    return extract(fixture_pdf(name), Settings(llm={"enabled": False}), debug=True)


def anchor(name: str, page: int, text: str) -> str | None:
    """The longest prefix of the text's first four words (two at least) found on the page.

    A table cell can merge with its neighbour on one baseline: f1 p60's trap "29(A) Contract
    Performance Security (CPS):" reads "29(A) Contract To ensure due performance …".
    """
    lines = [line.text for line in indexed_doc(name).pages[page - 1].lines]
    words = text.split()
    for n in range(min(4, len(words)), min(2, len(words)) - 1, -1):
        key = " ".join(words[:n])
        pattern = re.compile(r"(?<!\S)" + re.escape(key) + r"(?!\S)")
        if any(pattern.search(line) for line in lines):
            return key
    return None
