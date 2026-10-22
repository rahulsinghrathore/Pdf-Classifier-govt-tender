"""Stage 7: the LLM judges the undecided band (SPEC §7).

It sees one digest per candidate, with an explicit <<PAGE n>> marker, never the raw PDF, and
answers accept or reject. A decision whose evidence is not on the candidate's page is discarded and
the candidate rejected. Levels stay with the rules (§6): the trap safety net depends on that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from tender_sections.config import Settings
from tender_sections.ingest import normalize_text
from tender_sections.levels import assign_levels
from tender_sections.llm.client import LLMClient, LLMError
from tender_sections.llm.prompts import ADJUDICATE_SCHEMA, ADJUDICATE_SYSTEM
from tender_sections.models import (
    Candidate,
    IndexEntry,
    LLMUsage,
    Page,
    ParsedDocument,
    Warning,
    WarningCode,
)


class _Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: int
    decision: Literal["accept", "reject"]
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[_Decision]


@dataclass
class Adjudication:
    candidates: list[Candidate]
    warnings: list[Warning] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    transcripts: list[dict[str, Any]] = field(default_factory=list)


def adjudicate(
    candidates: list[Candidate],
    doc: ParsedDocument,
    llm: LLMClient,
    settings: Settings | None = None,
) -> Adjudication:
    """Every undecided candidate → accept or reject, batched per document."""
    settings = settings or Settings()
    cfg = settings.llm
    result = Adjudication(candidates=list(candidates))
    undecided = [i for i, c in enumerate(candidates) if c.decision == "undecided"]
    if not undecided:
        return result
    accepted = [c for c in assign_levels(candidates, settings) if c.decision == "accept"]
    entries: dict[str, IndexEntry] = {}
    for entry in doc.index_entries:
        entries.setdefault(entry.id_norm, entry)

    for start in range(0, len(undecided), cfg.max_candidates_per_call):
        batch = undecided[start : start + cfg.max_candidates_per_call]
        user = "\n\n".join(
            f"Candidate {n}\n{_digest(candidates[i], doc, accepted, entries, settings)}"
            for n, i in enumerate(batch, 1)
        )
        decisions, failure = _ask(llm, user, len(batch), settings, result)
        if failure is not None:
            code, problem = failure
            pages = sorted({candidates[i].line.page for i in batch})
            message = f"{problem}; undecided candidates rejected on pages {pages}"
            result.warnings.append(Warning(code=code, message=message))
        for n, i in enumerate(batch, 1):
            decision = decisions.get(n) if decisions else None
            result.candidates[i] = _apply(candidates[i], decision, doc, settings, result)
    return result


def evidence_on_page(evidence: str, page: Page) -> bool:
    """A case-insensitive substring of the page's non-boilerplate text."""
    needle = normalize_text(evidence).casefold()
    text = " ".join(line.text for line in page.lines if not line.is_boilerplate).casefold()
    return bool(needle) and needle in text


def _ask(
    llm: LLMClient, user: str, count: int, settings: Settings, result: Adjudication
) -> tuple[dict[int, _Decision] | None, tuple[WarningCode, str] | None]:
    """One call, and one retry with the validation error appended when the answer is invalid."""
    cfg = settings.llm
    prompt, problem = user, ""
    for attempt in (1, 2):
        try:
            reply = llm.complete_json(
                system=ADJUDICATE_SYSTEM,
                user=prompt,
                schema=ADJUDICATE_SCHEMA,
                max_tokens=cfg.max_tokens,
                effort=cfg.effort,
            )
        except LLMError as error:
            return None, ("LLM_UNAVAILABLE", f"LLM unavailable: {error}")
        result.usage.candidate_calls += 1
        result.usage.input_tokens += reply.input_tokens
        result.usage.output_tokens += reply.output_tokens
        result.transcripts.append(
            {"stage": "adjudicate", "attempt": attempt, "user": prompt, "answer": reply.text}
        )
        try:
            return _decisions(reply.data, count), None
        except ValueError as error:  # pydantic's ValidationError is a ValueError
            problem = str(error)
            prompt = (
                f"{user}\n\nYour previous answer was not valid: {problem}\n"
                f"Answer again, with exactly one decision for each candidate 1 to {count}."
            )
    return None, ("LLM_PARSE_FAILED", f"LLM answer invalid twice: {problem}")


def _decisions(data: Any, count: int) -> dict[int, _Decision]:
    answer = _Answer.model_validate(data)
    decided: dict[int, _Decision] = {}
    for decision in answer.decisions:
        if not 1 <= decision.candidate <= count:
            raise ValueError(f"candidate {decision.candidate} is not between 1 and {count}")
        if decision.candidate in decided:
            raise ValueError(f"candidate {decision.candidate} is decided twice")
        decided[decision.candidate] = decision
    missing = [n for n in range(1, count + 1) if n not in decided]
    if missing:
        raise ValueError(f"no decision for candidates {missing}")
    return decided


def _apply(
    candidate: Candidate,
    decision: _Decision | None,
    doc: ParsedDocument,
    settings: Settings,
    result: Adjudication,
) -> Candidate:
    if decision is None:  # no usable answer: as with the LLM off
        return candidate.model_copy(update={"decision": "reject", "decided_by": "disabled"})
    page = candidate.line.page
    if not evidence_on_page(decision.evidence, doc.pages[page - 1]):
        message = (
            f"evidence {decision.evidence!r} for {candidate.line.text!r} is not on page {page}; "
            "the decision is discarded and the candidate rejected"
        )
        result.warnings.append(Warning(code="LLM_EVIDENCE_MISMATCH", message=message, page=page))
        return candidate.model_copy(update={"decision": "reject", "decided_by": "llm"})
    return candidate.model_copy(
        update={
            "decision": decision.decision,
            "decided_by": "llm",
            "evidence": decision.evidence,
            "confidence": min(decision.confidence, settings.llm.confidence_cap),
        }
    )


def _digest(
    candidate: Candidate,
    doc: ParsedDocument,
    accepted: list[Candidate],
    entries: dict[str, IndexEntry],
    settings: Settings,
) -> str:
    page = doc.pages[candidate.line.page - 1]
    where = (candidate.line.page, candidate.line.order)
    before = [c for c in accepted if (c.line.page, c.line.order) < where]
    after = [c for c in accepted if (c.line.page, c.line.order) > where]
    printed = page.printed_number if page.printed_number is not None else "none"
    text = " ".join(
        line.text
        for line in page.lines
        if not line.is_boilerplate and line.order > candidate.line.order
    )
    limit = settings.llm.digest_chars
    excerpt = text[:limit] + ("…" if len(text) > limit else "")
    return "\n".join(
        [
            f"<<PAGE {page.number}>>  (physical; printed {printed})",
            f"Previous accepted heading: {_heading(before[-1] if before else None)}",
            f"Next accepted heading: {_heading(after[0] if after else None)}",
            f"Document's own index: {_listing(candidate, entries)}",
            f'Candidate line: "{candidate.line.text}"   [{", ".join(_flags(candidate, page, settings))}]',
            f"Page {page.number} text after the candidate (first {limit} characters):",
            f'"{excerpt}"',
        ]
    )


def _heading(candidate: Candidate | None) -> str:
    if candidate is None:
        return "none"
    name = " — ".join(part for part in (candidate.display_id, candidate.title) if part)
    return f'"{name or candidate.line.text}" (level {candidate.level}, page {candidate.line.page})'


def _listing(candidate: Candidate, entries: dict[str, IndexEntry]) -> str:
    if not entries:
        return "the document has no index"
    entry = entries.get(candidate.id_norm or "")
    if entry is None:
        return "does not list this line"
    description = f'"{entry.description}"' if entry.description else "no description"
    return f"{entry.display_id} = {description} ({entry.applicability}, page {entry.page})"


def _flags(candidate: Candidate, page: Page, settings: Settings) -> list[str]:
    line, cfg = candidate.line, settings.scoring
    if candidate.first_on_page:
        flags = ["first on page"]
    elif line.y0 < cfg.top_of_page_y:
        flags = ["near the top"]
    else:
        flags = ["mid-page"]
    size = f"{line.font_size:g} pt vs body {page.body_font_size:g}"
    if line.bold_ratio >= cfg.emphasis_bold_ratio:
        size += ", bold"
    if line.caps_ratio >= cfg.emphasis_caps_ratio:
        size += ", capitals"
    flags.append(size)
    flags.append(
        {
            "letter": f"lettered {candidate.id}.",
            "named": f"numbered {candidate.display_id}",
            "numeric": f"numbered clause {candidate.id}",
            "titled": f"no numbering; reads as {candidate.label}",
            "layout_only": "no numbering",
        }[candidate.kind]
    )
    if line.in_index_block:
        flags.append("inside the document's index list")
    elif line.in_table:
        flags.append("inside a table")
    notes = {
        "repeat_title": "repeats the previous heading's title",
        "letter_reuse": "its letter is already a top-level section",
        "unlisted_letter": "the contents do not list this letter",
        "sentence_like": "reads like a sentence",
    }
    flags += [note for key, note in notes.items() if key in candidate.score_breakdown]
    flags.append(f"score {candidate.score}/10")
    return flags
