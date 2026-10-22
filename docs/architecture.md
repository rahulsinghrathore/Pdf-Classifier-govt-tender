# Solution architecture

Part of the project docs; start at [README.md](../README.md). Why it is built this way: [decisions.md](decisions.md). Every algorithm in detail: [SPEC.md](SPEC.md).

## The problem, framed

This is hierarchical document segmentation, not search. A tender is a tree: top-level sections (lettered `A.`–`D.` in one tender, unlettered titles such as `NOTICE INVITING TENDER` in another), annexures nested by their numbers (`Annexure 2.6.1`), numbered clauses inside them. The pipeline finds the page where each section *starts*, computes in code where it *ends*, maps each title to a canonical label and resolves every target to the shallowest section carrying that label. It extracts the whole tree because the targets sit at different depths in different tenders, and because the tender's own annexure list is what tells "Not Applicable" from "missing".

## Pipeline

Stage numbers are the spec's. The LLM judge (7) runs between scoring and levels, and only on the lines scoring left undecided.

```
PDF bytes
  │  1 ingest       ingest.py        lines in reading order, with font, bold, capitals, box, table flags
  │  2 boilerplate  boilerplate.py   running headers/footers flagged; image-only pages decided (ocr.py if on)
  │  3 index        index_pages.py   the tender's contents and annexure lists → listed ids and Not Applicable
  │  4 candidates   candidates.py    heading-like lines of five kinds; a bare "Annexure 19" gets its title
  │  5 scoring      scoring.py       0–10 each: 8 or more accept, 3 or less reject, 4–7 undecided
  │  7 LLM judge    llm/             undecided lines only: accept or reject, with a quote verified on the page
  │  6 levels       levels.py        1 = top sections, 2 = Annexure N, one more per dot; sub-headings below
  │  8 assemble     assemble.py      the tree, end pages (the next heading outside the subtree), flat maps
  │  9 validate     validate.py      document checks; a failure → ONE whole-document LLM pass → 8 and 9 again
  │ 10 labels       labels.py        titles → labels; each target → the shallowest section carrying it
  ▼
ExtractionResult ─► command line (cli.py) · Streamlit app (app/) · evaluation harness (evaluate.py)
```

`extract()` in `__init__.py` runs this sequence and nothing else: every stage is a pure function from its input (and the settings) to its output.

## Deterministic core, LLM at the edges

- Stages 1–6 and 8–10 never import `tender_sections.llm` (`tests/test_architecture.py` checks the imports), and both test tenders reach their ground truth with the LLM off.
- The LLM sees one digest per undecided line — a `<<PAGE n>>` marker, the neighbouring headings, what the tender's index lists, the line with its flags, the text after it — never the PDF. Up to 40 lines go in one call, effort `low`.
- It answers accept or reject with an evidence quote. The quote is checked against the page's own text; an unverified answer is discarded and the line rejected. It is never asked for a level or a page range.
- At most one more call per document: when a stage-9 check fails, the LLM lists every section start from per-page digests (each entry verified the same way), and the tree is rebuilt and checked once. It never loops.

## Data flow

`ingest` builds a `ParsedDocument`: pages of `Line`s (text, box normalized to 0..1, font size, bold and capitals ratios, table flag), tables, bookmarks and the printed-page offset. Stages 2–3 add flags to lines, boilerplate groups and `IndexEntry`s. Stages 4–7 work on `Candidate`s: kind, id, title, label, score with a breakdown, decision, who decided, level, evidence. Stage 8 builds `Section`s: start page, inclusive and exclusive end, confidence, box, children. The `ExtractionResult` holds the targets with status and source, the tree, both flat maps, unassigned pages, listed-but-missing ids, warnings, `needs_human_review`, LLM usage and, on request, the debug data. All are pydantic models (`models.py`); pages are 1-based physical everywhere.

## When something goes wrong

| Situation | What happens |
|---|---|
| a document check fails: order, a listed target missing, Not Applicable found, odd length, no sections | one whole-document LLM pass; still failing → `needs_human_review`, command-line exit 2 |
| the LLM is off, or the API fails, refuses or is cut off | the undecided lines are rejected; warning `UNDECIDED_WITHOUT_LLM` or `LLM_UNAVAILABLE` |
| an answer is invalid, or quotes text that is not on the page | retried once, then `LLM_PARSE_FAILED`; the quote is discarded with `LLM_EVIDENCE_MISMATCH` |
| the LLM is on but `ANTHROPIC_API_KEY` is missing | `LLMNotConfigured`: the command line exits 1, the app shows the error |
| a page is an image with no text layer | it falls inside the section around it (`PAGE_IMAGE_ONLY`); with OCR on, tesseract reads it (`OCR_UNAVAILABLE` if it cannot) |

Every warning carries a stable code from SPEC §9 and, where it has one, a page.

## Around the pipeline

- **Command line** (`cli.py`): `extract` and `eval`; JSON only on stdout, warnings and the `--debug` candidate table on stderr; exit 0, 2 for review, 1 for errors.
- **Streamlit app** (`app/streamlit_app.py`): draws pages as PNGs cached per file, page and resolution, boxes each heading, and shows the targets strip with Sections, JSON, Checks and Debug tabs. Results are cached per file and settings hash. It holds no pipeline logic and imports only the package's public names.
- **Evaluation harness** (`evaluate.py`): runs `extract()` over labelled tenders and reports SPEC §15's metrics, with a guessed error bucket per mistake.
- **Settings** (`config.py`): every number in one `Settings` object; YAML and `TENDER_*` variables override the defaults.
- **Claude API** (`llm/client.py`): `claude-sonnet-5-5` unless `LLM_MODEL` says otherwise; answers constrained by a JSON schema (structured outputs); the server-side refusal fallback on; the SDK retries rate limits and server errors.

## Quality gates

Unit tests per stage on tiny synthetic PDFs; the contract tests on two hand-verified tenders; the LLM and OCR replaced by scripted fakes, with a guard that makes any real API client fail in tests; the app driven headless by Streamlit's `AppTest`; the import rules checked on the source. New tenders are measured with the evaluation harness before any weight is tuned.
