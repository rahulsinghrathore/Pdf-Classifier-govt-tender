# CLAUDE.md — Tender Section Extractor

## What this project is

A Python tool that takes a government tender PDF and returns the page ranges of five business-defined sections, plus the full section tree they were found in:

```json
{"targets": {"pqc": [11, 13], "atc": [15, 16], "scc": [69, 78], "sor": [58, 68], "tech_spec": [79, 85]},
 "targets_status": {"pqc": "found", "atc": "found", "scc": "found", "sor": "found", "tech_spec": "found"}}
```

When a tender does not contain one of them, the value is `null` and the status says *why*: `not_applicable` (the tender's own annexure list says so — e.g. a GeM supply tender with no SCC) or `absent` (we found nothing and the document did not say). Those are different answers and the business needs both.

Plus a Streamlit UI: upload a PDF, PDF rendered on the left half, targets strip + section tree on the right half, click a section to jump to its page, download the JSON.

The problem is **hierarchical document segmentation**: find the page where each section *starts*; compute where it *ends* in code; map titles to labels; resolve each target to the shallowest section carrying that label. The five targets live at different levels in different tenders — top-level lettered sections in one, Annexures 19/20/21 in another — so the pipeline must extract the whole tree and resolve labels anywhere in it.

Two fixture PDFs with hand-verified ground truth are the contract; both must reach it **with the LLM disabled**:

- `tests/fixtures/nrl_pur1011567.{pdf,expected.json}` — supply tender, 67 pp, lettered `A.–D.` sections, SCC/SOR/Tech Specs **Not Applicable**
- `tests/fixtures/nrl_pur1011848.{pdf,expected.json}` — works tender, 85 pp, **unlettered** top sections, SCC/SOR/Tech Specs are Annexures 20/19/21, two image-only drawing pages at the end

## Where the rest lives

- [README.md](README.md) — overview, quick start, usage. [docs/architecture.md](docs/architecture.md), [docs/decisions.md](docs/decisions.md) — how it fits together, and why. [docs/files/](docs/files/root.md) — what each file does.
- [docs/SPEC.md](docs/SPEC.md) — the design, indexed by section (`SPEC §5c`); one file per pair of stages in `docs/spec/`. Read a stage's file before touching its module.
- [docs/layout.md](docs/layout.md) — stack and repo layout. [docs/milestones.md](docs/milestones.md) — build order and status.
- [docs/pitfalls.md](docs/pitfalls.md) — things that look like good ideas and are not.
- Every Markdown file stays under 80 lines: split by topic rather than grow one.

## Hard rules

Each one is here because it was the cause of a wrong answer on a fixture. Do not "simplify" them away.

1. **The LLM never computes end pages.** `assemble.py` does: a section ends the page before the next heading outside its own subtree starts (same page if that heading starts mid-page). The subtree, not the level: an orphan `Annexure 7.2` (no `Annexure 7`) hangs under the level-1 section, so it ends `Annexure 6`. Both inclusive (parent covers children) and exclusive (parent stops at first child) ranges are emitted.
2. **The LLM is a judge, not a parser.** It sees per-page digests with explicit `<<PAGE n>>` markers and the candidate lines, never the raw PDF. It is called only for candidates scoring 4–7 and for at most **one** whole-document fallback pass. Every LLM decision carries an `evidence` string verified to exist on the claimed page; unverified decisions are discarded.
3. **Deterministic stages run without the LLM.** `ingest`, `boilerplate`, `index_pages`, `candidates`, `scoring`, `levels`, `assemble`, `validate`, `labels` must not import anything from `tender_sections.llm`.
4. **No RAG / embeddings / chunking / vector store.** The only similarity step is matching a *heading title* to the label vocabulary in `labels.py`, with keyword rules first and fuzzy matching second.
5. **Sort lines by y and merge same-baseline fragments before anything else.** PyMuPDF block order is not reading order (fixture 1 p52, p25, p59).
6. **Strip running headers/footers before deciding what is "top of page".** Exact text (spacing ignored: fixture 1 pp41–42 print `No. :` where other pages print `No.:`) repeated in the top/bottom band on ≥ 3 pages. Not a percentage (headers change at p14 of fixture 1), not digit-normalized (would merge `Annexure 2` and `Annexure 3`), never a `letter`/`named` heading line. Vocabulary titles used as running headers (`SPECIAL CONDITIONS OF CONTRACT` on fixture 2 pp71–78) **are** stripped; a re-admission rule brings the first occurrence back only if no section carries that label.
7. **Decide "image-only page" after boilerplate, not before.** Fixture 2 pp84–85 have 42 chars of footer and nothing else. They need no OCR: the end-page rule places them inside Technical Specifications.
8. **Lines inside tables or index blocks get −5.** Contents pages, annexure lists, checklist cells and cross-references are the main source of false headings. The page's own title above such a block (`D. TENDER ANNEXURES`, `LIST OF ANNEXURES`) is real and must not be penalized.
9. **Unlettered headings are recognised through the vocabulary, not by font alone.** `NOTICE INVITING TENDER` at 10 pt bold on fixture 2 is a level-1 section because it maps to `nit`; a 12 pt bold unnumbered line that maps to nothing (`Information for transporter / goods carrier`, fixture 1 p17) goes to the LLM.
10. **A repeated title is not a new section.** The same label within 2 pages of an accepted heading (`SCHEDULE OF RATES` on p59 after `Annexure 19` on p58) gets −5 — unless the line carries a new id (fixture 1 Annexures 8, 9, 10 are all `declarations`).
11. **Bare `Annexure N` lines take their title from the largest emphasized line group below them, then from the index description.** `Annexure 20` → `SPECIAL CONDTIONS OF CONTRACT` (sic) → label `scc`.
12. **A target resolves to the shallowest section with that label.** `2. Technical Specification:` inside Annexure 21 never wins over Annexure 21.
13. **Page numbers are 1-based physical everywhere internally.** Printed numbers are detected only from the series whose `of N` equals the page count (fixture 2's SOR has its own `SOR Page X of 10` footer) and stored as an offset.
14. **All numbers live in `config.py`.** Weights, thresholds (accept ≥ 8, reject ≤ 3), bands, repeat window, max depth, target labels, vocabulary.
15. **Never edit `tests/fixtures/*.expected.json` to make a test pass.** If you believe the ground truth is wrong, stop and show the page in question.
16. **No network in tests.** LLM tests use `FakeLLMClient`.
17. **The Streamlit app contains no pipeline logic.** It imports `tender_sections.extract` and renders the result.

## Commands

```bash
pip install -r requirements.txt && pip install -e .   # into .venv (python3.12 -m venv .venv)
pytest -q                                 # all tests; must be green before any commit
pytest tests/test_e2e_fixture.py -q       # the contract tests (both fixtures, LLM disabled)
python -m tender_sections extract tender.pdf --no-llm   # targets as JSON; --full, --debug (SPEC §12)
streamlit run app/streamlit_app.py        # the UI (SPEC §13)
python -m tender_sections eval eval/labelled --report eval/report.md   # SPEC §15
ruff check . && ruff format .             # Markdown is excluded: ruff would rewrite its code blocks
```

## Working conventions

- Type hints everywhere; pydantic models at module boundaries; plain functions inside stages. Stage functions are pure: `pages_in → pages_out` or `candidates_in → candidates_out`.
- Every warning has a stable `code` from SPEC §9. New codes go into the SPEC table, not ad hoc.
- When a heuristic changes, run both fixtures with `--debug` and diff the candidate tables before and after. A change that fixes one document and breaks a fixture is rejected.
- Commit messages: `stage: what changed — why (fixture effect)`. One stage per commit where possible.
- When a design question is not answered by the spec, ask before implementing. Likely ones: physical vs printed page in the output (default physical), whether GPC/SCC numbered clauses should be emitted (default no), a sixth target label (one line in config).
