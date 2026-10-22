"""Streamlit UI (SPEC §13): the PDF on the left, the extracted structure on the right.

    streamlit run app/streamlit_app.py

No pipeline logic here (CLAUDE.md hard rule 17): the page calls tender_sections.extract and
renders its result. PyMuPDF only draws pages.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pymupdf
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw

from tender_sections import ExtractionResult, Section, Settings, extract

DPI = 110
MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5")
KEPT_RESULTS = 8  # results per session, one per (file, settings)
DOT = {"found": "🟢", "not_applicable": "⚪", "absent": "🔴"}
NAMES = {"pqc": "PQC", "atc": "ATC", "scc": "SCC", "sor": "SOR", "tech_spec": "Tech Specs"}
HIGHLIGHT = (220, 38, 38)


def main() -> None:
    st.set_page_config(page_title="Tender Section Extractor", layout="wide")
    settings, show_debug, problem = sidebar()
    st.title("Tender Section Extractor")
    upload_col, run_col, status_col = st.columns([4, 1, 7], vertical_alignment="bottom")
    uploaded = upload_col.file_uploader("Upload PDF", type=["pdf"], key="upload")
    if uploaded is None:
        st.info("Upload a tender PDF to begin.")
        return
    pdf, name = uploaded.getvalue(), uploaded.name
    file_hash = hashlib.sha256(pdf).hexdigest()
    try:
        pages = page_count(file_hash, pdf)
    except (RuntimeError, ValueError) as error:  # pymupdf.FileDataError is a RuntimeError
        st.error(f"Cannot read {name}: {error}")
        return
    if st.session_state.get("file_hash") != file_hash:
        st.session_state.file_hash, st.session_state.page = file_hash, 1

    results: dict[str, dict[str, Any]] = st.session_state.setdefault("results", {})
    key = f"{file_hash}:{hashlib.sha256(settings.model_dump_json().encode()).hexdigest()[:16]}"
    if run_col.button("Run", type="primary", key="run", disabled=problem is not None):
        with status_col:
            run(pdf, name, settings, key, results)
    entry = results.get(key)
    if entry is not None:
        status_col.caption(stage_line(entry))

    left, right = st.columns([1, 1], gap="medium")
    result: ExtractionResult | None = entry["result"] if entry else None
    with left:
        viewer(file_hash, pdf, pages, result)
    with right:
        if result is None:
            other = any(k.startswith(file_hash) for k in results)
            st.info("Settings changed: press Run again." if other else "Press Run to extract.")
        else:
            show(result, name, show_debug)


def sidebar() -> tuple[Settings, bool, str | None]:
    defaults = Settings()
    with st.sidebar:
        st.header("Settings")
        llm_on = st.toggle("Ask the LLM about unsure lines", defaults.llm.enabled, key="llm")
        model = st.selectbox(
            "Model",
            ["default", *MODELS],
            key="model",
            disabled=not llm_on,
            help="default: LLM_MODEL from .env, else claude-sonnet-5-5",
        )
        accept = st.slider("Accept at score ≥", 0, 10, defaults.scoring.accept_at, key="accept")
        reject = st.slider("Reject at score ≤", 0, 10, defaults.scoring.reject_at, key="reject")
        depth = st.number_input(
            "Deepest level emitted", 1, 8, defaults.levels.max_emit_level, step=1, key="depth"
        )
        targets = st.multiselect(
            "Target labels",
            list(defaults.labels.vocabulary),
            default=list(defaults.labels.target_labels),
            key="targets",
        )
        show_debug = st.toggle("Show debug", key="show_debug")
        problem = None
        if reject >= accept:
            problem = "The reject score must be below the accept score."
        elif not targets:
            problem = "Choose at least one target label."
        if problem:
            st.error(problem)
    llm: dict[str, Any] = {"enabled": llm_on}
    if model != "default":
        llm["model"] = model
    settings = Settings(
        llm=llm,
        scoring={"accept_at": accept, "reject_at": reject},
        levels={"max_emit_level": int(depth)},
        labels={"target_labels": tuple(targets)},
    )
    return settings, show_debug, problem


def run(
    pdf: bytes, name: str, settings: Settings, key: str, results: dict[str, dict[str, Any]]
) -> None:
    stages: list[tuple[str, str]] = []
    with st.status("Extracting…", expanded=True) as status:

        def on_stage(stage: str, detail: str) -> None:
            stages.append((stage, detail))
            status.write(f"{stage} ✓ {detail}")

        try:
            result = extract(pdf, settings, debug=True, on_stage=on_stage)
        except Exception as error:  # shown, not raised: a missing API key, a locked PDF
            st.error(f"Extraction failed: {error}")
            status.update(label="Extraction failed", state="error", expanded=True)
            return
        calls = result.llm_usage.candidate_calls + int(result.llm_usage.whole_doc_pass)
        status.update(label=f"Done · LLM calls: {calls}", state="complete", expanded=False)
    document = result.document.model_copy(update={"file": name})
    results[key] = {"result": result.model_copy(update={"document": document}), "stages": stages}
    while len(results) > KEPT_RESULTS:
        results.pop(next(iter(results)))


def stage_line(entry: dict[str, Any]) -> str:
    usage = entry["result"].llm_usage
    calls = usage.candidate_calls + int(usage.whole_doc_pass)
    return " · ".join(
        f"{stage} ({calls}) ✓" if stage == "llm" else f"{stage} ✓" for stage, _ in entry["stages"]
    )


# PDF viewer --------------------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def page_count(file_hash: str, _pdf: bytes) -> int:
    with pymupdf.open(stream=_pdf, filetype="pdf") as doc:
        return doc.page_count


@st.cache_data(show_spinner=False, max_entries=256)
def render_page(file_hash: str, page: int, dpi: int, _pdf: bytes) -> bytes:
    """PNG of one page, cached by (file_hash, page, dpi); the bytes are not hashed."""
    with pymupdf.open(stream=_pdf, filetype="pdf") as doc:
        return doc[page - 1].get_pixmap(dpi=dpi).tobytes("png")


def goto(page: int) -> None:
    st.session_state.page = page


def step(delta: int, pages: int) -> None:
    st.session_state.page = min(max(st.session_state.page + delta, 1), pages)


def viewer(file_hash: str, pdf: bytes, pages: int, result: ExtractionResult | None) -> None:
    st.session_state.page = min(max(int(st.session_state.get("page", 1)), 1), pages)
    back, number, forward = st.columns([1, 3, 1], vertical_alignment="bottom")
    current = st.session_state.page
    back.button("◀", key="prev", on_click=step, args=(-1, pages), disabled=current <= 1)
    number.number_input(f"Page (of {pages})", min_value=1, max_value=pages, step=1, key="page")
    forward.button("▶", key="next", on_click=step, args=(1, pages), disabled=current >= pages)
    page = st.session_state.page
    boxes = (
        [s.bbox for s in walk(result.sections) if s.start_page == page and s.bbox] if result else []
    )
    try:
        png = render_page(file_hash, page, DPI, pdf)
    except (RuntimeError, ValueError) as error:
        st.warning(f"Cannot draw page {page}: {error}")
    else:
        st.image(highlight(png, boxes), width="stretch")
    if st.toggle("Embed original PDF", key="embed", help="Some browsers block data-URI PDFs"):
        data = base64.b64encode(pdf).decode()
        frame = f'<iframe src="data:application/pdf;base64,{data}#page={page}" width="100%" height="860"></iframe>'
        components.html(frame, height=880)


def highlight(png: bytes, boxes: list[tuple[float, float, float, float]]) -> bytes | Image.Image:
    """The page with a frame around each heading that starts on it."""
    if not boxes:
        return png
    image = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for x0, y0, x1, y1 in boxes:
        frame = (x0 * width - 4, y0 * height - 3, x1 * width + 4, y1 * height + 3)
        draw.rectangle(frame, outline=HIGHLIGHT, width=3)
    return image


# Results -----------------------------------------------------------------------------------------


def show(result: ExtractionResult, name: str, show_debug: bool) -> None:
    targets_strip(result)
    tabs = st.tabs(["Sections", "JSON", "Checks", *(["Debug"] if show_debug else [])])
    with tabs[0]:
        sections_tab(result)
    with tabs[1]:
        json_tab(result, name, show_debug)
    with tabs[2]:
        checks_tab(result)
    if show_debug:
        with tabs[3]:
            debug_tab(result)


def targets_strip(result: ExtractionResult) -> None:
    st.markdown("**Targets**")
    by_id = {section.id: section for section in walk(result.sections)}
    labels = list(result.targets)
    for row in range(0, len(labels), 3):
        for column, label in zip(st.columns(3), labels[row : row + 3], strict=False):
            status, span = result.targets_status[label], result.targets[label]
            source = result.targets_source.get(label)
            entry = source.index_entry if source else None
            page: int | None = None
            if span is not None:
                text, page = f"p{span[0]}–{span[1]}", span[0]
                section = by_id.get(source.section or "") if source else None
                tip = heading(section) if section else "found"
            elif status == "not_applicable":
                text = "N/A"
                page = entry.page if entry else None
                tip = (
                    f"listed as Not Applicable on p{entry.page} ({entry.display_id})"
                    if entry
                    else "listed as Not Applicable"
                )
            else:
                text = "absent"
                page = entry.page if entry else None
                tip = (
                    f"listed on p{entry.page} ({entry.display_id}) but no section was found"
                    if entry
                    else "no section, and the tender's own index does not list it"
                )
            name = NAMES.get(label, label.replace("_", " ").upper())
            column.button(
                f"{DOT[status]} **{name}** {text}",
                key=f"target_{label}",
                help=tip,
                on_click=goto,
                args=(page,),
                disabled=page is None,
                width="stretch",
            )


def sections_tab(result: ExtractionResult) -> None:
    if not result.sections:
        st.warning("No sections were found.")
    for top in result.sections:
        with st.expander(f"{md(heading(top))}  ·  p{top.start_page}–{top.end_page}"):
            for section, depth in walk_depth([top]):
                text, go = st.columns([9, 1], vertical_alignment="center")
                badges = [confidence_badge(section.confidence)]
                if section.label != "other":
                    badges.insert(0, f":blue-badge[{section.label}]")
                if section.decided_by.startswith("llm"):
                    badges.append(":violet-badge[LLM]")
                text.markdown(
                    f"{'&emsp;' * depth}{md(heading(section))} · "
                    f"p{section.start_page}–{section.end_page} {' '.join(badges)}"
                )
                go.button("Go", key=f"go_{section.id}", on_click=goto, args=(section.start_page,))
    if result.unassigned_pages:
        st.caption(f"Pages in no section: {page_ranges(result.unassigned_pages)}")


def json_tab(result: ExtractionResult, name: str, show_debug: bool) -> None:
    stem = Path(name).stem
    targets = {"targets": result.targets, "targets_status": result.targets_status}
    st.json(targets)
    view = st.radio(
        "Flat map",
        ["Inclusive", "Exclusive"],
        horizontal=True,
        key="flat_view",
        help="Inclusive: a parent covers its children. Exclusive: it stops at its first child.",
    )
    st.json(result.flat_inclusive if view == "Inclusive" else result.flat_exclusive, expanded=1)
    full = result.model_dump(mode="json", exclude=None if show_debug else {"debug"})
    st.json(full, expanded=False)
    sections = {
        "sections": full["sections"],
        "flat_inclusive": result.flat_inclusive,
        "flat_exclusive": result.flat_exclusive,
        "unassigned_pages": result.unassigned_pages,
    }
    files = (("targets", targets), ("sections", sections), ("full", full))
    for column, (part, payload) in zip(st.columns(3), files, strict=True):
        column.download_button(
            f"{part}.json",
            json.dumps(payload, indent=2, ensure_ascii=False),
            file_name=f"{stem}.{part}.json",
            mime="application/json",
            key=f"download_{part}",
        )


def checks_tab(result: ExtractionResult) -> None:
    if result.needs_human_review:
        st.error("Needs human review: a document-level check failed (see the warnings).")
    else:
        st.success("No document-level check failed.")
    if result.expected_but_missing:
        st.markdown(f"**Listed but not found:** {', '.join(result.expected_but_missing)}")
    if result.not_applicable_found:
        st.markdown(f"**Not Applicable but found:** {', '.join(result.not_applicable_found)}")
    by_code: dict[str, list[str]] = {}
    for warning in result.warnings:
        page = f"p{warning.page}: " if warning.page is not None else ""
        by_code.setdefault(warning.code, []).append(page + warning.message)
    for code, messages in by_code.items():
        with st.expander(f"{code} ({len(messages)})"):
            for message in messages:
                st.markdown(md(message))
    if not by_code:
        st.caption("No warnings.")


def debug_tab(result: ExtractionResult) -> None:
    debug = result.debug
    if debug is None:
        st.info("No debug data in this result.")
        return
    st.markdown("**Candidates**")
    st.dataframe(
        [
            {
                "page": c.line.page,
                "text": c.line.text,
                "kind": c.kind,
                "score": c.score,
                "breakdown": " ".join(f"{k}={v:+d}" for k, v in c.score_breakdown.items()),
                "decision": c.decision,
                "decided_by": c.decided_by,
                "level": c.level,
                "label": c.label,
            }
            for c in debug.candidates
        ],
        hide_index=True,
    )
    st.markdown("**Boilerplate lines**")
    st.dataframe(
        [
            {"page": line.page, "text": line.text, "y0": round(line.y0, 3)}
            for line in debug.boilerplate_lines
        ],
        hide_index=True,
    )
    st.markdown("**Index entries**")
    st.dataframe([entry.model_dump() for entry in debug.index_entries], hide_index=True)
    st.markdown(f"**LLM transcripts** ({len(debug.llm_transcripts)})")
    for number, transcript in enumerate(debug.llm_transcripts, 1):
        with st.expander(f"Call {number}"):
            st.json(transcript, expanded=False)


# Helpers -----------------------------------------------------------------------------------------


def walk(sections: list[Section]) -> Iterator[Section]:
    for section, _ in walk_depth(sections):
        yield section


def walk_depth(sections: list[Section], depth: int = 0) -> Iterator[tuple[Section, int]]:
    for section in sections:
        yield section, depth
        yield from walk_depth(section.children, depth + 1)


def heading(section: Section) -> str:
    """The heading as printed (B. PRE-QUALIFICATION…), with a looked-up title after a bare id."""
    if not section.title or section.title in section.evidence:
        return section.evidence
    return f"{section.display_id} — {section.title}" if section.display_id else section.title


def confidence_badge(confidence: float) -> str:
    colour = "green" if confidence >= 0.85 else "orange" if confidence >= 0.6 else "red"
    return f":{colour}-badge[{confidence:.2f}]"


def md(text: str) -> str:
    """Text shown as written: titles hold *, _ and $, which Streamlit reads as Markdown or LaTeX."""
    return re.sub(r"([\\`*_\[\]<>$#|~])", r"\\\1", text)


def page_ranges(pages: list[int]) -> str:
    runs: list[list[int]] = []
    for page in pages:
        if runs and page == runs[-1][1] + 1:
            runs[-1][1] = page
        else:
            runs.append([page, page])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs)


main()
