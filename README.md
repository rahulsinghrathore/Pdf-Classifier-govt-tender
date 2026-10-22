# Tender Section Extractor

Give it a government tender PDF and it returns the page ranges of the five sections the business asked for, plus the tender's whole section tree. Scoring rules do the work; Claude is asked only about the few lines the rules are unsure of, and every answer must quote the page it is about. A command line, a Streamlit app and an evaluation harness all call the same function.

**Read next:** [architecture](docs/architecture.md) · [design decisions](docs/decisions.md) · [using the app](docs/ui/guide.md) · [what each file does](docs/files/root.md) · [the spec](docs/SPEC.md) · [rules for changing the code](CLAUDE.md)

## What it returns

```json
{"targets": {"pqc": [11, 13], "atc": [15, 16], "scc": [69, 78], "sor": [58, 68], "tech_spec": [79, 85]},
 "targets_status": {"pqc": "found", "atc": "found", "scc": "found", "sor": "found", "tech_spec": "found"}}
```

The labels: `pqc` pre-qualification criteria, `atc` agreed terms and conditions, `scc` special conditions of contract, `sor` schedule of rates, `tech_spec` technical specifications. Pages are 1-based physical pages, and a range includes both ends. A target the tender lacks is `null`, and its status says why: `not_applicable` when the tender's own annexure list says so, `absent` when nothing was found and the tender does not say. The full result adds the section tree, page maps of every section, warnings, a `needs_human_review` flag and the LLM's token use.

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
python -m tender_sections extract tests/fixtures/nrl_pur1011848.pdf --no-llm
```

The rules alone reproduce both test tenders, so `--no-llm` needs no key. To let Claude judge the unsure lines, create `.env` with `ANTHROPIC_API_KEY=…` and optionally `LLM_MODEL=claude-sonnet-5-5`; `.env` is gitignored, never commit it. OCR for scanned pages is optional and off: `pip install -e ".[ocr]"`, install the tesseract program, set `ocr.enabled: true`.

## Usage

| Task | Command |
|---|---|
| Targets of one tender | `python -m tender_sections extract tender.pdf [--no-llm] [--config config.yaml]` |
| The whole result; the candidate table on stderr | `python -m tender_sections extract tender.pdf --full --debug > out.json` |
| The app: the PDF on the left, its sections on the right | `streamlit run app/streamlit_app.py` |
| Score against labelled tenders | `python -m tender_sections eval eval/labelled --report eval/report.md` |

The command line writes only JSON on stdout and exits 0, or 2 when the result needs human review, or 1 on an error. From Python:

```python
from tender_sections import Settings, extract

result = extract("tender.pdf", Settings(llm={"enabled": False}))
print(result.targets, result.targets_status, result.needs_human_review)
```

## How it works

Ten stages turn the PDF into a section tree ([architecture](docs/architecture.md)): **ingest** the lines in reading order → strip running headers and footers (**boilerplate**; OCR image-only pages if enabled) → read the tender's own contents and annexure lists (**index**) → find heading **candidates** → **score** each 0–10: 8 or more is accepted, 3 or less rejected → the **LLM** judges the 4–7 band → **levels** → **assemble** the tree and compute every end page → **validate** the document (a failed check gets one whole-document LLM pass, then goes to human review) → map titles to **labels** and resolve the targets.

The LLM never reads the PDF and never computes a page range. Every stage but the LLM's runs, and is tested, without it.

## Repository

| Path | What is there | Every file explained |
|---|---|---|
| `src/tender_sections/` | the pipeline: one module per stage, the data model, the settings | [pipeline](docs/files/pipeline.md) |
| `src/tender_sections/llm/`, `cli.py`, `evaluate.py`, `app/`, `eval/` | the LLM judge, the command line, the harness, the app | [interfaces](docs/files/interfaces.md) |
| `tests/` | stage tests, the two fixture tenders, end-to-end and system tests | [tests](docs/files/tests.md) · [system tests](docs/files/tests-system.md) |
| `docs/` | the spec (one file per pair of stages), architecture, decisions, plans | [docs](docs/files/docs.md) |
| the root | packaging, dependencies, default settings, contributor rules | [root](docs/files/root.md) |

## Configuration

Every number the pipeline uses — score weights, thresholds, the label vocabulary, the target labels, the LLM's model and effort, OCR — lives in [config.py](src/tender_sections/config.py), and [config.yaml](config.yaml) lists the same defaults (a test keeps them equal). Precedence: code defaults < a `--config` file < `TENDER_<SECTION>__<KEY>` environment variables (`TENDER_SCORING__ACCEPT_AT=9`) < arguments in code. A sixth target label is one entry in `labels.target_labels`.

## Testing

```bash
pytest -q                            # everything; no test reaches the network
pytest tests/test_e2e_fixture.py -q  # the contract: both tenders, LLM off
ruff check . && ruff format .
```

Two hand-verified NRL tenders are the contract (`tests/fixtures/`): a 67-page supply tender with lettered sections, where SCC, SOR and technical specifications are listed as Not Applicable, and an 85-page works tender with unlettered sections and its targets in Annexures 19–21. Their `.expected.json` files are never edited to make a test pass. Tests use a scripted LLM and a scripted OCR engine. Before changing a stage, read its spec file and CLAUDE.md's hard rules.

## Status and limits

Milestones 1–7 are built ([milestones](docs/milestones.md)). Still open: labelled tenders from issuers other than NRL, a scanned test tender, and a run with the real tesseract. Not handled yet: two-column layouts, Hindi headings, and very long tenders in the fallback pass ([SPEC §16](docs/spec/tests-eval.md)).
