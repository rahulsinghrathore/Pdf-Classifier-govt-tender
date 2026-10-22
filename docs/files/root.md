# Files: the repository root

File reference: **root** · [pipeline](pipeline.md) · [interfaces](interfaces.md) · [tests](tests.md) · [system tests](tests-system.md) · [docs](docs.md). Start at [README.md](../../README.md).

- **[`README.md`](../../README.md)** — The front page for someone new to the project: what the tool returns,
  how to install and run it, the pipeline in one paragraph, configuration, testing and status.
  Links to the architecture, the design decisions and this file reference.
- **[`CLAUDE.md`](../../CLAUDE.md)** — The rules for anyone changing the code, person or coding agent: 17 hard
  rules, each caused by a wrong answer on a test tender, plus the commands and working conventions.
  Claude Code loads it into every session; the spec decides *how*, CLAUDE.md *what you may not do*.
- **[`pyproject.toml`](../../pyproject.toml)** — The package `tender-sections` (Python ≥ 3.11, built from `src/`
  with hatchling): its dependencies, the `tender-sections` command, and the `ocr` and `dev` extras.
  Also the pytest settings (test paths, a warning filter) and ruff's rules (line length 100, Markdown excluded).
- **[`requirements.txt`](../../requirements.txt)** — What a working environment needs, as version ranges: pydantic,
  pydantic-settings, PyYAML, PyMuPDF, rapidfuzz, anthropic, streamlit, pillow, python-dotenv, pytest and ruff.
  `pytesseract` is listed but commented out: OCR is optional.
- **[`config.yaml`](../../config.yaml)** — Every setting at its default value, one section per stage, from `ingest`
  to `llm`. Copy it, edit it, and pass it with `--config`; `TENDER_*` environment variables override it.
  `tests/test_config.py` fails if it drifts from the defaults in `config.py`.
- **`.env`** (local only, not in git) — The secrets the LLM client reads: `ANTHROPIC_API_KEY` and, optionally,
  `LLM_MODEL` (default `claude-sonnet-5-5`). Only needed while the LLM is on.
  Variables already set in the environment win over it; `.gitignore` keeps it out of the repository.
- **[`.gitignore`](../../.gitignore)** — Keeps secrets and generated files out of git: `.env`, the virtual
  environment, Python and tool caches, build output, and the generated `eval/report.md`.
  The fixture PDFs are not ignored: they are part of the test contract.
