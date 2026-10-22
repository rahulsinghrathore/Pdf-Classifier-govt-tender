# Tests, evaluation, known limitations (§14–16)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 14. Tests (`tests/`)

Parametrize over both fixtures wherever the check is generic.

- `test_config.py`: `config.yaml` equals the code defaults; environment overrides; unknown keys rejected; the heading patterns.
- `test_ingest.py`: page counts (67 / 85); f1 p52 first line by y is `Annexure 18`; f1 p25 has the merged `D. Benefits…` line; f2 printed offset is 0 and `SOR Page X of 10` is ignored.
- `test_boilerplate.py`: §4 checks; f2 `image_only_pages == [84, 85]`.
- `test_index_pages.py`: §5a counts and applicability; f2 `17` is `external`.
- `test_candidates.py`: bare-id title lookup gives the `annexure_titles_from_body` of f2.
- `test_scoring.py`: every `traps.must_accept` entry scores ≥ 8; every `traps.must_reject_or_demote` entry is found on its page (a check that finds nothing proves nothing) and scores ≤ 7; the safety net: every trap that reaches the LLM (4–7: f1 p17, f2 p1, f2 p31) still lands at level ≥ 3 if accepted, except f2 p1 `PART–I: UNPRICED BID` — a Part heading, so level 1 (§6), protected only by the LLM rejecting cover labels (§7); traps the rules reject never reach the LLM; the §5c worked examples; rules alone accept exactly the expected sections; numbered clauses skip the LLM while not emitted.
- `test_levels.py`: f2 unlettered level-1 headings get level 1; `7.2` orphan rule; titled line consumed as a bare-id title.
- `test_assemble.py`: pure-function tests with synthetic headings (nested levels, mid-page starts, orphans).
- `test_validate.py`: synthetic cases per warning code; f2 single missing `17` does **not** trigger the fallback.
- `test_labels.py`: vocabulary table incl. `CONDTIONS` typo → `scc`; f2 p29 MSE line → **not** `scc`; target resolution picks shallowest.
- `test_e2e_fixture.py` (parametrized): LLM disabled → `targets`, `targets_status`, `flat_inclusive`, `flat_exclusive`, section levels, `unassigned_pages` all equal the expected JSON; fallback did not fire; `UNDECIDED_WITHOUT_LLM` pages are exactly f1 `{17}`, f2 `{1, 29, 31, 32, 70, 80}`.
- `test_extract.py`: `extract()` on synthetic documents — re-admission of a running title that is the only heading, a blank PDF.
- `test_llm_adjudicate.py`: `FakeLLMClient` returns an `evidence` string absent from the page → rejected with `LLM_EVIDENCE_MISMATCH`; retry once on an invalid answer, then `LLM_PARSE_FAILED`; `LLM_UNAVAILABLE`; batching; the digest shows `<<PAGE n>>` and the line, never the PDF; both fixtures reach ground truth when the fake rejects the band; the trap safety net through the fake.
- `test_llm_whole_doc.py`: the fallback rebuilds a document the checks failed; one call, never a loop; unverifiable entries dropped; an unavailable LLM leaves the document for review.
- `test_cli.py`: targets by default, `--full`, `--debug` (the table on stderr), exit 2 for review and 1 for errors (usage, unreadable input, bad config, a missing API key against a stubbed SDK), `python -m` writes only JSON, both fixtures' targets.
- `test_app.py`: AppTest drives the UI headless: upload, Run, the targets strip, Go buttons, a settings change asks for a new run, the Debug tab, the review banner, a failure shown not raised, f1's tooltip "listed as Not Applicable on p15".
- `test_ocr.py`: a scripted engine: a section that starts on a scanned page is found; OCR lines are merged and measured like text-layer lines; a footer is not doubled; no engine, or an engine error → `OCR_UNAVAILABLE`; the tesseract adapter against a stub module; f2 unchanged with OCR on.
- `test_evaluate.py`: both fixtures score 100% with no errors; truths perturbed in memory put each kind of error in its bucket; the `eval` command.
- `test_architecture.py`: hard rules 3 and 17, checked on the imports.
- `conftest.py`: the LLM is off in every test unless a fake is handed in, and building the real client fails.

Helpers: `tests/helpers.py` (fixtures, skipped while a PDF is absent, and cached stage outputs), `tests/pdfgen.py` (synthetic PDFs), `tests/synthetic.py` (synthetic candidates for levels / assemble / validate), `tests/fakes.py` (scripted LLM answers, a scripted OCR engine).

Fixture PDFs: `tests/fixtures/nrl_pur1011567.pdf` (3 MB) and `tests/fixtures/nrl_pur1011848.pdf` (3.8 MB). Commit directly or via Git LFS.

## 15. Evaluation harness (`eval/`)

`eval/labelled/<name>.pdf` + `<name>.expected.json` (same shape as the fixtures). `run_eval.py` reports per document and aggregate:
- **target accuracy**: per label, exact `[start, end]` match (±0 pages) and status match — this is the business metric
- **start-page exact match rate** per level
- **section F1** at levels 1 and 2 (id + exact start page)
- **nesting accuracy**, **false heading rate**
- **LLM call rate** (% documents, % candidates) and token cost
- error buckets: `index_page`, `cross_reference`, `repeat_title`, `mid_page`, `ocr`, `boilerplate`, `level`, `label`, `other`

Code: `tender_sections/evaluate.py`, run by `python -m tender_sections eval` or `eval/run_eval.py`; the labelled format is in [eval/labelled/README.md](../../eval/labelled/README.md). How it counts:
- A section is its id and start page. Per-level counts use the truth's level: `tree_levels`, else 1 for an id in `level1_titles`.
- Nesting: among sections found at their start page, the parent id is right. The truth's parent is the deepest lower-level section whose range holds the section (an orphan `7.2` → the level-1 section, as in §8).
- False headings: emitted sections whose (id, start page) the truth lacks. LLM band: candidates the LLM judged, or rejected for want of one.
- Buckets are a first guess from the debug data (an index page, an image-only page, a label repeated within the window, running-header text, reference wording, a mid-page start, a wrong level or parent, a target on the wrong section): a pointer to a cause, not a score.

On the fixtures with the LLM off: every metric 100%, no errors; 13 of 661 candidates in the LLM band.

Target before calling v1 done: ≥ 50 labelled tenders across ≥ 5 issuers (CPPP, GeM, PSU formats like NRL/IOCL/ONGC, state portals), at least 10 scanned, at least 5 bilingual.

## 16. Known limitations / later

- Two-column layouts: y-sort interleaves columns; detect column gutters before sorting if such tenders appear.
- Bilingual (Hindi/English) headings: vocabulary and regex need Devanagari variants (`अनुबंध`, `अनुलग्नक`, `खंड`, `निविदा सूचना`); OCR engine must support Devanagari.
- Corrigenda merged in front of the tender shift printed vs physical pages — handled by `printed_page_offset`; make physical/printed a CLI/UI switch.
- Very large documents (> 300 pages): chunk the whole-document fallback digest by level-1 section.
- Sections that start on an image-only page need OCR (milestone 7); image-only pages *inside* a section do not.
