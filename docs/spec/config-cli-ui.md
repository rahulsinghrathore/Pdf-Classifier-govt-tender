# Config, CLI and Streamlit UI (§11–13)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 11. Config (`config.py`)

Single pydantic `Settings` object, loadable from `config.yaml` + env overrides. Sections: `ingest`, `boilerplate`, `text_layer`, `ocr`, `patterns`, `index`, `candidates`, `scoring`, `labels` (vocabulary, target labels), `levels`, `checks` (stage 9); `llm` (§7: enabled, model, effort, batch size, digest lengths, confidence cap, refusal fallback). Precedence: code defaults < `config.yaml` < `TENDER_<SECTION>__<KEY>` environment variables < keyword arguments. A test keeps `config.yaml` equal to the code defaults. Everything numeric in this spec lives here: band sizes and `boilerplate.min_pages`, index-block thresholds, score weights, thresholds (8/3), `repeat_title.window_pages` (2), `max_emit_level`, `emit_numeric_clauses`, `target_labels`, vocabulary (overridable per issuer), LLM model/enabled/max candidates per call, OCR enabled/engine/dpi/languages/word confidence, suspicious-length ratio. No magic numbers in stage modules.

## 12. CLI (`cli.py`)

```
python -m tender_sections extract path/to/tender.pdf [--no-llm] [--config config.yaml] [--full] [--debug] > out.json
python -m tender_sections eval  eval/labelled/  --report eval/report.md
```

`extract` prints `targets` (+ `targets_status`) by default, the whole `ExtractionResult` with `--full`; warnings to stderr; exit 0 (2 if `needs_human_review`).

- `--debug` writes the candidate table on stderr (page, kind, score, decision, decided_by, level, label, text, score breakdown; one row per candidate) for diffing before and after a heuristic change, and with `--full` adds the `debug` block to the JSON. stdout carries JSON only.
- Exit 1 on an error: an unreadable PDF or config file, `ANTHROPIC_API_KEY` missing while the LLM is on, bad arguments (argparse's usual 2 would read as "review").
- `eval` scores a folder (§15): the summary JSON on stdout, the Markdown report with `--report`. Both commands take `--no-llm` and `--config`; `pip install -e .` also installs them as `tender-sections`.

## 13. Streamlit UI (`app/streamlit_app.py`)

Purpose: upload a tender, PDF on the left, extracted structure on the right, click a section to jump to its page, download the JSON. For users: [docs/ui/guide.md](../ui/guide.md).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Tender Section Extractor                                [sidebar: settings] │
│  [ Upload PDF ]  [ Run ]   status: ingest ✓ boilerplate ✓ scoring ✓ llm (0) ✓│
├──────────────────────────────────┬───────────────────────────────────────────┤
│  PDF viewer (col 1)              │  Results (col 2)                          │
│  ◀  page [ 58 ] / 85  ▶          │  TARGETS                                   │
│  ┌────────────────────────────┐  │   PQC   p11–13  ●   ATC  p15–16  ●         │
│  │  rendered page PNG         │  │   SCC   p69–78  ●   SOR  p58–68  ●         │
│  │  heading bbox highlighted  │  │   Tech Specs p79–85 ●   (grey = N/A, red = absent) │
│  │                            │  │  tabs: Sections | JSON | Checks | Debug   │
│  │                            │  │  ▸ NIT                        p2–10        │
│  │                            │  │  ▸ PQC                        p11–13       │
│  │                            │  │  ▾ LIST OF ANNEXURES          p17–85       │
│  └────────────────────────────┘  │      Annexure 19  SOR         p58–68 [Go] │
└──────────────────────────────────┴───────────────────────────────────────────┘
```

- `st.set_page_config(layout="wide")`; `left, right = st.columns([1, 1], gap="medium")`.
- Upload via `st.file_uploader(type=["pdf"])`. Key results by `sha256(bytes) + settings hash` in `st.session_state`. Run inside `st.status()` with one line per stage (`extract(on_stage=…)` reports each) and the LLM call count. The run always collects debug data, so the debug toggle needs no new run.
- **PDF viewer**: `page.get_pixmap(dpi=110)` → PNG, cached with `@st.cache_data` keyed by `(file_hash, page_no, dpi)`. Prev/next buttons and `st.number_input` bound to `st.session_state.page`. If the current page has an accepted heading, draw its bbox (`Section.bbox`, PIL) before display. Optional "Embed original PDF" toggle → `<iframe src="data:application/pdf;base64,…">` via `st.components.v1.html`, off by default (some browsers block data-URI PDFs). Do not add `streamlit-pdf-viewer` unless the PNG approach proves insufficient.
- **Targets strip** (top of right column, always visible): five tiles, each clickable → jumps the viewer to the start page. Colour: green `found`, grey `not_applicable` with tooltip "listed as Not Applicable on p15" (from `targets_source`; the tile jumps to that page), red `absent`.
- **Sections tab**: tree with `st.expander` per level-1 section; row = display id, title, label chip, `p{start}–{end}`, confidence badge (green ≥ 0.85, amber 0.6–0.85, red < 0.6), `LLM` tag when `decided_by` starts with `llm`, `Go` button → `st.session_state.page = start_page`. Row for `unassigned_pages` at the bottom.
- **JSON tab**: `st.json(targets)` first; radio `Inclusive | Exclusive` for the flat map; then the full `ExtractionResult`; download buttons `<file>.targets.json`, `<file>.sections.json`, `<file>.full.json`.
- **Checks tab**: warnings grouped by code; `expected_but_missing`, `not_applicable_found`, `needs_human_review` banner.
- **Debug tab** (sidebar toggle): `st.dataframe` of candidates (page, text, kind, score, breakdown, decision, decided_by, level), boilerplate lines, index entries, LLM transcripts.
- **Sidebar**: LLM on/off, model, accept/reject thresholds (sliders 0–10, default 8/3), `max_emit_level`, target labels (multiselect, default the five), show debug. Any change invalidates the cache key. Defaults are the code's plus `TENDER_*` variables; the UI does not read `config.yaml`.
- The UI imports `tender_sections.extract` and nothing else from the package internals: only the public names `extract`, `Settings`, `ExtractionResult`, `Section` (`tests/test_architecture.py` checks it). No pipeline logic in the UI.
