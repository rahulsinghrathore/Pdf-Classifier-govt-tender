# Stack and repo layout

Part of the project docs; start at [CLAUDE.md](../CLAUDE.md).

## Stack

- Python 3.11+, `pydantic` v2 + `pydantic-settings`, `pymupdf` (import as `pymupdf`, not `fitz`), `rapidfuzz`, `anthropic` SDK, `streamlit`, `pillow`, `pytest`, `ruff`.
- Optional OCR behind an interface (`pytesseract` or PaddleOCR). Off by default; not needed for either fixture.
- Secrets via env only: `ANTHROPIC_API_KEY`, `LLM_MODEL` (default `claude-sonnet-5-5`). Never commit keys. `.env` is gitignored.

## Layout

One line per file here; three lines per file, page by page, in the file reference ([files/](files/root.md)).

```
README.md                        # the front page: what it returns, quick start, usage, status
CLAUDE.md                        # rules, commands, conventions (always loaded)
docs/SPEC.md                     # index of the design; the sections live in docs/spec/*.md
docs/architecture.md  docs/decisions.md   # how the solution fits together; why it is built this way
docs/layout.md  docs/milestones.md  docs/pitfalls.md
docs/ui/guide.md  docs/ui/tabs.md   # user guide to the app: every control, tab and message
docs/files/*.md                  # the file reference: root, pipeline, interfaces, tests, system tests, docs
pyproject.toml  requirements.txt
config.yaml                      # defaults; a test keeps it equal to Settings in config.py
src/tender_sections/
  __init__.py                    # extract(pdf, settings=None, *, llm=None, ocr=None, debug=False, on_stage=None)
  __main__.py                    # python -m tender_sections → cli.main
  config.py                      # Settings; all tunables incl. target_labels and vocabulary
  models.py                      # Line, Page, IndexEntry, Candidate, Section, ExtractionResult, Warning
  headings.py                    # letter / named / numeric heading patterns, shared by stages 2–4
  ingest.py                      # PyMuPDF → Pages/Lines; bookmarks; printed page numbers
  ocr.py                         # OCR interface, tesseract engine, apply_ocr (off by default)
  boilerplate.py                 # running header/footer flags; image-only page decision; re-admission
  index_pages.py                 # contents / annexure-list blocks → IndexEntry list
  candidates.py                  # letter / named / numeric / titled / layout_only; bare-id title lookup
  scoring.py                     # 0–10 score + breakdown + accept/reject/undecided (two passes)
  levels.py                      # level inference, title consumption, emission
  llm/                           # the only LLM code (CLAUDE.md hard rule 3)
    client.py                    # LLMClient protocol, AnthropicClient, FakeLLMClient
    prompts.py
    adjudicate.py                # undecided candidates → decisions (evidence-verified)
    whole_doc.py                 # one-shot fallback pass (evidence-verified)
  assemble.py                    # tree, end pages (inclusive + exclusive), flat maps, unassigned pages
  validate.py                    # checks → warnings → fallback trigger → needs_human_review
  labels.py                      # vocabulary, label_for(), resolve_targets()
  cli.py                         # python -m tender_sections extract|eval; also the command tender-sections
  evaluate.py                    # SPEC §15 metrics, error buckets, the Markdown report
app/streamlit_app.py             # SPEC §13; imports only the package's public names
tests/
  fixtures/nrl_pur1011567.pdf  fixtures/nrl_pur1011567.expected.json
  fixtures/nrl_pur1011848.pdf  fixtures/nrl_pur1011848.expected.json
  test_config.py test_ingest.py test_boilerplate.py test_index_pages.py test_candidates.py
  test_scoring.py test_labels.py test_levels.py test_assemble.py test_validate.py
  test_extract.py                # extract() on synthetic documents (re-admission, a blank PDF)
  test_e2e_fixture.py            # the contract: both fixtures, LLM disabled
  test_llm_adjudicate.py         # stage 7 with FakeLLMClient; the safety net through the fake
  test_llm_whole_doc.py          # the one whole-document fallback pass
  test_cli.py test_app.py        # the command line; the UI driven headless (AppTest)
  test_ocr.py test_evaluate.py   # OCR with a scripted engine; the harness on the fixtures
  test_architecture.py           # hard rules 3 and 17, checked on the imports
  conftest.py                    # no network: LLM off in tests, the real client refuses to build
  helpers.py                     # fixture access (skips while a PDF is absent), cached stages
  pdfgen.py synthetic.py fakes.py  # synthetic PDFs; synthetic candidates; scripted LLM and OCR
eval/
  run_eval.py                    # the harness as a script: python eval/run_eval.py eval/labelled
  labelled/README.md             # the format of a labelled tender (<name>.pdf + <name>.expected.json)
```
