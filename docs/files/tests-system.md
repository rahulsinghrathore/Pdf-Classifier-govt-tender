# Files: end-to-end and system tests (`tests/`)

File reference: [root](root.md) · [pipeline](pipeline.md) · [interfaces](interfaces.md) · [tests](tests.md) · **system tests** · [docs](docs.md). Start at [README.md](../../README.md).

- **[`test_extract.py`](../../tests/test_extract.py)** — `extract()` on synthetic documents, for paths the fixtures never take: a running
  title that is the only heading carrying its label comes back (the re-admission rule), and a blank PDF
  asks for human review with `NO_SECTIONS`.
- **[`test_e2e_fixture.py`](../../tests/test_e2e_fixture.py)** — The contract: both fixtures, LLM off, must equal their ground truth exactly:
  targets and status, both flat maps, levels, top-level titles, unassigned pages, listed-but-missing ids, page facts.
  The fallback must not fire, the undecided pages are exactly f1 {17} and f2 {1, 29, 31, 32, 70, 80}.
- **[`test_llm_adjudicate.py`](../../tests/test_llm_adjudicate.py)** — Stage 7 with the scripted LLM: verdicts with capped confidence, what a
  digest shows (page markers, neighbours, never the PDF), evidence mismatches, retry then parse failure, an
  unavailable LLM, batching. Both fixtures reach ground truth when the LLM says no; the safety net holds when it says yes.
- **[`test_llm_whole_doc.py`](../../tests/test_llm_whole_doc.py)** — The whole-document fallback with the scripted LLM: a document that failed
  `NO_SECTIONS` is rebuilt; the request names the failed checks and marks every page; unverifiable entries are
  dropped; one call, never a loop; a wrapped title is found by its first line.
- **[`test_cli.py`](../../tests/test_cli.py)** — The command line: targets by default, `--full`, `--debug` (the table on stderr), exit 2 for
  review and 1 for errors (bad arguments, unreadable PDF, bad config, a missing API key against a stubbed SDK).
  `python -m` writes nothing but JSON, and both fixtures print their expected targets.
- **[`test_app.py`](../../tests/test_app.py)** — The Streamlit app driven headless by `AppTest`: upload, Run, the targets strip, Go buttons
  and tiles moving the viewer, a settings change asking for a new run, crossed thresholds, the Debug tab, the
  review banner, failures shown rather than raised, and f1's tooltip "listed as Not Applicable on p15".
- **[`test_ocr.py`](../../tests/test_ocr.py)** — OCR with the scripted engine: a section that starts on a scanned page is found, OCR lines are
  merged and measured like text, a footer is not doubled, no engine or a failing one gives `OCR_UNAVAILABLE`.
  Also the tesseract adapter against a stub module, and f2 unchanged with OCR on.
- **[`test_evaluate.py`](../../tests/test_evaluate.py)** — The harness: both fixtures score 100% with no errors; truths perturbed in memory
  (never on disk) put a wrong level, an index-page heading, a miss on a drawing page and a wrong label each in its
  bucket. Also the `eval` command: the report, skipped files, errors.
- **[`test_architecture.py`](../../tests/test_architecture.py)** — CLAUDE.md's import rules, checked on the source with `ast`: no deterministic
  stage (nor `ocr.py`) imports `tender_sections.llm`, and the app imports only names in `tender_sections.__all__`.
  Nothing is executed; it reads the import statements.
