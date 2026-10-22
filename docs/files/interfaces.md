# Files: the LLM, the command line, the harness and the app

File reference: [root](root.md) · [pipeline](pipeline.md) · **interfaces** · [tests](tests.md) · [system tests](tests-system.md) · [docs](docs.md). Start at [README.md](../../README.md).

## The LLM (`src/tender_sections/llm/`)

- **[`llm/__init__.py`](../../src/tender_sections/llm/__init__.py)** — The package's public names: the clients, `adjudicate` and
  `whole_document_pass`. This package is the only place the LLM is used: stage 7 and the whole-document fallback.
  No deterministic stage imports it (CLAUDE.md hard rule 3).
- **[`llm/client.py`](../../src/tender_sections/llm/client.py)** — The `LLMClient` protocol (`complete_json(...) -> LLMReply`) and two clients.
  `AnthropicClient` calls Claude with the answer schema as structured output, the effort setting and the refusal
  fallback, reading `ANTHROPIC_API_KEY` / `LLM_MODEL` from the environment or `.env`; `FakeLLMClient` is scripted for tests.
- **[`llm/prompts.py`](../../src/tender_sections/llm/prompts.py)** — The two system prompts and their JSON answer schemas: adjudication (per line:
  decision, evidence, confidence, reason) and the whole-document pass (per section: page, id, title, level, evidence).
  The adjudication prompt lists what is no section start: index rows, cross-references, cover labels, repeated titles.
- **[`llm/adjudicate.py`](../../src/tender_sections/llm/adjudicate.py)** — Stage 7: one digest per undecided line (`<<PAGE n>>`, neighbouring headings,
  the index's listing, the line and its flags, the text after it), batched into calls of up to 40 lines.
  Checks every quote against the page; retries an invalid answer once; caps confidence at 0.85; never asks for levels.
- **[`llm/whole_doc.py`](../../src/tender_sections/llm/whole_doc.py)** — The one whole-document pass when a stage-9 check fails: every page's
  first 300 characters and candidate lines, the index, the current result and the failed checks, in one call.
  An entry must quote a line on its page (a wrapped title matches by its first line); the kept ones become the headings.

## Command line and harness (`src/tender_sections/`)

- **[`__main__.py`](../../src/tender_sections/__main__.py)** — Makes `python -m tender_sections` run the command line: it calls `cli.main`
  and exits with its status. Nothing else is in it.
  The installed command `tender-sections` (from `pyproject.toml`) calls the same function.
- **[`cli.py`](../../src/tender_sections/cli.py)** — The command line: `extract` (targets by default; `--full`, `--debug`, `--no-llm`, `--config`)
  and `eval` (`--report`). JSON only on stdout; warnings, errors and the candidate table on stderr.
  Exit 0, 2 when the result needs human review, 1 on any error, bad arguments included.
- **[`evaluate.py`](../../src/tender_sections/evaluate.py)** — The evaluation harness (SPEC §15): `extract()` over pairs of `<name>.pdf` and
  `<name>.expected.json`, scoring targets, start pages per level, section F1, nesting, false headings and LLM use.
  Gives every mistake a guessed error bucket (index page, repeated title, OCR …); `render_report` writes the Markdown.

## The app and the evaluation folder

- **[`app/streamlit_app.py`](../../app/streamlit_app.py)** — The Streamlit UI: upload a PDF and press Run; the page is drawn on the left with its
  headings boxed, the targets strip and the Sections / JSON / Checks / Debug tabs on the right, with JSON downloads.
  Sidebar settings key a per-session result cache. No pipeline logic: it imports only the package's public names.
- **[`eval/run_eval.py`](../../eval/run_eval.py)** — The harness as a script, the same as `python -m tender_sections eval`: for example
  `python eval/run_eval.py eval/labelled --report eval/report.md`. It hands its arguments to `cli.main`.
  The report it writes, `eval/report.md`, is generated and not committed.
- **[`eval/labelled/README.md`](../../eval/labelled/README.md)** — How to add a labelled tender: a `<name>.pdf` with a hand-verified
  `<name>.expected.json` next to it. Lists the four keys the harness reads and the section-id conventions.
  The folder holds no tenders yet: tenders from other issuers are the next step.
