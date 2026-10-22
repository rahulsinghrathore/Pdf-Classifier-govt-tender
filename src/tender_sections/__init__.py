"""Tender Section Extractor: page ranges of business-defined sections in tender PDFs.

Design: docs/SPEC.md. Rules: CLAUDE.md. The UI and CLI use `extract` and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tender_sections.assemble import assemble
from tender_sections.boilerplate import lines_to_readmit, mark_boilerplate
from tender_sections.candidates import find_candidates
from tender_sections.config import Settings
from tender_sections.index_pages import mark_index_blocks
from tender_sections.ingest import ingest
from tender_sections.labels import label_for_text, resolve_targets
from tender_sections.levels import assign_levels, emitted
from tender_sections.llm import (
    AnthropicClient,
    FakeLLMClient,
    LLMClient,
    adjudicate,
    whole_document_pass,
)
from tender_sections.models import (
    Candidate,
    DebugInfo,
    DocumentInfo,
    ExtractionResult,
    LLMUsage,
    ParsedDocument,
    Section,
)
from tender_sections.ocr import OCREngine, apply_ocr
from tender_sections.scoring import reject_undecided, score_candidates
from tender_sections.validate import validate

__version__ = "0.1.0"
__all__ = ["ExtractionResult", "FakeLLMClient", "LLMClient", "Section", "Settings", "extract"]


def extract(
    pdf: bytes | str | Path,
    settings: Settings | None = None,
    *,
    llm: LLMClient | None = None,
    ocr: OCREngine | None = None,
    debug: bool = False,
    on_stage: Callable[[str, str], None] | None = None,
) -> ExtractionResult:
    """Stages 1–10 on one tender PDF.

    The LLM judges the undecided band and, when a stage-9 check fails the document, gets one
    whole-document pass. Pass `llm` to use a given client (tests: FakeLLMClient); otherwise the
    Anthropic client is built when first needed, unless settings.llm.enabled is off, in which case
    the band is rejected and named in an UNDECIDED_WITHOUT_LLM warning. With settings.ocr.enabled,
    image-only pages are read by `ocr` (default: the configured engine). `on_stage(stage, detail)`
    is called as each stage finishes: the UI's status lines.
    """
    settings = settings or Settings()
    client: LLMClient | None = llm
    report = on_stage or _quiet

    def judge() -> LLMClient | None:
        nonlocal client
        if client is None and settings.llm.enabled:
            client = AnthropicClient(settings.llm)
        return client

    doc = ingest(pdf, settings)
    report("ingest", f"{doc.page_count} pages")
    doc = mark_boilerplate(doc, settings)
    report("boilerplate", _boilerplate_detail(doc))
    if any(page.needs_ocr for page in doc.pages):
        doc = apply_ocr(doc, pdf, settings, ocr)
        read = [page.number for page in doc.pages if page.ocr]
        report("ocr", f"read pages {read}" if read else "unavailable (see warnings)")
    doc = mark_index_blocks(doc, settings)
    report("index", f"{len(doc.index_entries)} listed ids")
    candidates = score_candidates(find_candidates(doc, settings), doc, settings)
    candidates = _readmit(candidates, doc, settings)
    report("scoring", _scoring_detail(candidates))

    usage, transcripts = LLMUsage(), []
    unsure = sum(c.decision == "undecided" for c in candidates)
    if unsure and (judged_by := judge()) is not None:
        adjudication = adjudicate(candidates, doc, judged_by, settings)
        candidates, llm_warnings = adjudication.candidates, adjudication.warnings
        usage, transcripts = adjudication.usage, adjudication.transcripts
        report("llm", f"{usage.candidate_calls} call(s) for {unsure} lines")
    else:
        candidates, llm_warnings = reject_undecided(candidates)
        report("llm", f"off: {unsure} lines rejected" if unsure else "nothing to judge")
    candidates = assign_levels(candidates, settings)

    assembly = assemble(emitted(candidates, settings), doc.page_count)
    report("assemble", f"{len(assembly.flat)} sections")
    checks = validate(assembly, doc, settings)
    report("validate", f"failed: {', '.join(sorted(checks.triggers))}" if checks.triggers else "ok")
    rebuilt: list[Candidate] = []
    if checks.triggers and (judged_by := judge()) is not None:
        failing = [w for w in checks.warnings if w.code in checks.triggers]
        fallback = whole_document_pass(doc, candidates, assembly, failing, judged_by, settings)
        llm_warnings += fallback.warnings
        transcripts += fallback.transcripts
        usage = LLMUsage(
            candidate_calls=usage.candidate_calls,
            whole_doc_pass=True,
            input_tokens=usage.input_tokens + fallback.usage.input_tokens,
            output_tokens=usage.output_tokens + fallback.usage.output_tokens,
        )
        if fallback.headings:  # re-assemble and re-validate once; never loop
            rebuilt = fallback.headings
            assembly = assemble(rebuilt, doc.page_count)
            checks = validate(assembly, doc, settings)
        report("fallback", f"1 call, {len(fallback.headings)} verified headings")

    targets = resolve_targets(assembly.flat, doc.index_entries, settings.labels)
    found = sum(status == "found" for status in targets.status.values())
    report("labels", f"{found} of {len(targets.status)} targets found")
    return ExtractionResult(
        document=DocumentInfo(
            file=doc.file_name,
            pages=doc.page_count,
            printed_page_offset=doc.printed_page_offset,
            has_bookmarks=bool(doc.bookmarks),
            image_only_pages=[page.number for page in doc.pages if page.is_image_only],
            needs_ocr_pages=[page.number for page in doc.pages if page.needs_ocr],
        ),
        targets=targets.ranges,
        targets_status=targets.status,
        targets_source=targets.sources,
        sections=assembly.sections,
        flat_inclusive=assembly.flat_inclusive,
        flat_exclusive=assembly.flat_exclusive,
        unassigned_pages=assembly.unassigned_pages,
        expected_but_missing=checks.expected_but_missing,
        not_applicable_found=checks.not_applicable_found,
        warnings=[*doc.warnings, *llm_warnings, *checks.warnings],
        needs_human_review=bool(checks.triggers),
        llm_usage=usage,
        debug=_debug(doc, [*candidates, *rebuilt], transcripts) if debug else None,
    )


def _readmit(
    candidates: list[Candidate], doc: ParsedDocument, settings: Settings
) -> list[Candidate]:
    """SPEC §4 step 6: a stripped running title whose label no accepted section carries comes
    back as a titled candidate, and everything is scored again. A no-op on both fixtures."""
    accepted = {c.label for c in candidates if c.decision == "accept"}
    lines = lines_to_readmit(doc, lambda text: label_for_text(text, settings.labels), accepted)
    if not lines:
        return candidates
    readmitted = [
        Candidate(
            line=line,
            kind="titled",
            title=line.text,
            title_source="same_line",
            label=label_for_text(line.text, settings.labels),
            first_on_page=all(
                other.is_boilerplate or other.order >= line.order
                for other in doc.pages[line.page - 1].lines
            ),
        )
        for line in lines
    ]
    # A re-admitted line that opens its page takes "first on page" from the line that had it.
    opened = {c.line.page for c in readmitted if c.first_on_page}
    candidates = [
        c.model_copy(update={"first_on_page": False}) if c.line.page in opened else c
        for c in candidates
    ]
    merged = sorted([*candidates, *readmitted], key=lambda c: (c.line.page, c.line.order))
    return score_candidates(merged, doc, settings)


def _quiet(stage: str, detail: str) -> None:
    pass


def _boilerplate_detail(doc: ParsedDocument) -> str:
    running = sum(line.is_boilerplate for page in doc.pages for line in page.lines)
    image_only = [page.number for page in doc.pages if page.is_image_only]
    return f"{running} running lines" + (f", image-only pages {image_only}" if image_only else "")


def _scoring_detail(candidates: list[Candidate]) -> str:
    accepted = sum(c.decision == "accept" for c in candidates)
    undecided = sum(c.decision == "undecided" for c in candidates)
    return f"{len(candidates)} candidates, {accepted} accepted, {undecided} undecided"


def _debug(doc: ParsedDocument, candidates: list[Candidate], transcripts: list[dict]) -> DebugInfo:
    return DebugInfo(
        candidates=candidates,
        llm_transcripts=transcripts,
        boilerplate_lines=[
            line for page in doc.pages for line in page.lines if line.is_boilerplate
        ],
        index_entries=doc.index_entries,
    )
