"""The one whole-document LLM pass, run when a stage-9 check fails the document (SPEC §9).

One call at most. The LLM lists every section start; an entry whose evidence is not a line on the
page it names is dropped. The caller re-assembles and re-validates once and never loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from tender_sections.assemble import Assembly
from tender_sections.config import Settings
from tender_sections.headings import match_heading
from tender_sections.ingest import normalize_text
from tender_sections.labels import label_for
from tender_sections.llm.client import LLMClient, LLMError
from tender_sections.llm.prompts import WHOLE_DOC_SCHEMA, WHOLE_DOC_SYSTEM
from tender_sections.models import Candidate, Line, LLMUsage, Page, ParsedDocument, Warning


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    id: str
    title: str
    level: int
    evidence: str


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[_Entry]


@dataclass
class WholeDocument:
    headings: list[Candidate] = field(default_factory=list)  # verified starts, in document order
    warnings: list[Warning] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=lambda: LLMUsage(whole_doc_pass=True))
    transcripts: list[dict[str, Any]] = field(default_factory=list)


def whole_document_pass(
    doc: ParsedDocument,
    candidates: list[Candidate],
    assembly: Assembly,
    failing: list[Warning],
    llm: LLMClient,
    settings: Settings | None = None,
) -> WholeDocument:
    settings = settings or Settings()
    cfg = settings.llm
    result = WholeDocument()
    user = _request(doc, candidates, assembly, failing, settings)
    try:
        reply = llm.complete_json(
            system=WHOLE_DOC_SYSTEM,
            user=user,
            schema=WHOLE_DOC_SCHEMA,
            max_tokens=cfg.max_tokens,
            effort=cfg.whole_doc_effort,
        )
    except LLMError as error:
        result.warnings.append(
            Warning(
                code="LLM_UNAVAILABLE", message=f"whole-document pass: LLM unavailable: {error}"
            )
        )
        return result
    result.usage.input_tokens += reply.input_tokens
    result.usage.output_tokens += reply.output_tokens
    result.transcripts.append({"stage": "whole_doc", "user": user, "answer": reply.text})
    try:
        answer = _Answer.model_validate(reply.data)
    except ValueError as error:
        result.warnings.append(
            Warning(
                code="LLM_PARSE_FAILED", message=f"whole-document pass: invalid answer: {error}"
            )
        )
        return result

    descriptions = {e.id_norm: e.description for e in doc.index_entries if e.description}
    seen: set[tuple[int, int]] = set()
    for entry in answer.sections:
        heading = _heading(entry, doc, descriptions, settings)
        if heading is None:
            message = f"whole-document pass: {entry.evidence!r} is not a line on page {entry.page}; dropped"
            page = entry.page if 1 <= entry.page <= doc.page_count else None
            result.warnings.append(
                Warning(code="LLM_EVIDENCE_MISMATCH", message=message, page=page)
            )
            continue
        where = (heading.line.page, heading.line.order)
        if where not in seen:
            seen.add(where)
            result.headings.append(heading)
    result.headings.sort(key=lambda h: (h.line.page, h.line.order))
    return result


def _heading(
    entry: _Entry, doc: ParsedDocument, descriptions: dict[str, str], settings: Settings
) -> Candidate | None:
    if not 1 <= entry.page <= doc.page_count:
        return None
    page = doc.pages[entry.page - 1]
    line = _line_with(entry.evidence, page)
    if line is None:
        return None
    match = match_heading(line.text, settings.patterns)
    id_norm = match.id_norm if match else None
    title = entry.title or (match.title if match else line.text)
    content = [other for other in page.lines if not other.is_boilerplate]
    return Candidate(
        line=line,
        kind=match.kind if match else "titled",
        id=match.id if match else None,
        id_norm=id_norm,
        display_id=match.display_id if match else entry.id,
        title=title,
        title_source="same_line",
        label=label_for(title, descriptions.get(id_norm or ""), settings.labels),
        first_on_page=content[0].order == line.order,
        decision="accept",
        decided_by="llm_whole_doc",
        level=min(max(entry.level, 1), settings.levels.max_emit_level),
        evidence=entry.evidence,
        confidence=settings.llm.confidence_cap,
    )


def _line_with(evidence: str, page: Page) -> Line | None:
    """The line holding the evidence, or the first line of a heading that wraps onto the next."""
    needle = normalize_text(evidence).casefold()
    if not needle:
        return None
    content = [line for line in page.lines if not line.is_boilerplate]
    for line in content:
        if needle in line.text.casefold():
            return line
    for line in content:
        if needle.startswith(line.text.casefold()):
            return line
    return None


def _request(
    doc: ParsedDocument,
    candidates: list[Candidate],
    assembly: Assembly,
    failing: list[Warning],
    settings: Settings,
) -> str:
    limit = settings.llm.whole_doc_page_chars
    parts = ["Checks that failed:"]
    parts += [f"- {w.code}: {w.message}" for w in failing]
    if doc.index_entries:
        parts.append("\nThe document's own index:")
        for e in doc.index_entries:
            described = f'"{e.description}"' if e.description else "no description"
            parts.append(f"- {e.display_id}: {described} ({e.applicability}, page {e.page})")
    else:
        parts.append("\nThe document has no index.")
    parts.append("\nCurrent result (section, level, pages):")
    parts += [
        f"- {s.id} (level {s.level}): pages {s.start_page}–{s.end_page}" for s in assembly.flat
    ]
    if not assembly.flat:
        parts.append("- none")
    parts.append("\nPages:")
    by_page: dict[int, list[Candidate]] = {}
    for c in candidates:
        by_page.setdefault(c.line.page, []).append(c)
    for page in doc.pages:
        text = " ".join(line.text for line in page.lines if not line.is_boilerplate)
        parts.append(f"<<PAGE {page.number}>>")
        parts.append(text[:limit] + ("…" if len(text) > limit else ""))
        found = by_page.get(page.number, [])
        if found:
            listed = "; ".join(f'"{c.line.text}" [score {c.score}, {c.decision}]' for c in found)
            parts.append(f"Heading-like lines: {listed}")
    return "\n".join(parts)
