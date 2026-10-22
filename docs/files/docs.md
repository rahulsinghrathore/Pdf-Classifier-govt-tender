# Files: the documentation (`docs/`)

File reference: [root](root.md) · [pipeline](pipeline.md) · [interfaces](interfaces.md) · [tests](tests.md) · [system tests](tests-system.md) · **docs**. Start at [README.md](../../README.md).

## Project docs

- **[`SPEC.md`](../SPEC.md)** — The index of the design spec: a table from each § number to its file in `spec/`, and the two
  fixtures side by side. Code and docs cite the spec by number (`SPEC §5c`).
  Where it and CLAUDE.md disagree, the spec wins on *how*, CLAUDE.md on *what you may not do*.
- **[`architecture.md`](../architecture.md)** — The solution architecture: the problem as hierarchical segmentation, the pipeline
  stage by stage, where the LLM is used and where it is not, the data flow, what happens when something goes
  wrong, and the parts around the pipeline.
- **[`decisions.md`](../decisions.md)** — The design decisions and their reasons: framing, pipeline rules, the LLM, interfaces
  and process. Most cite the fixture page that forced them.
  The rules they became are in CLAUDE.md; the failed alternatives in `pitfalls.md`.
- **[`layout.md`](../layout.md)** — The stack (Python 3.11+, pydantic, PyMuPDF, rapidfuzz, anthropic, streamlit) and the
  repository tree with a one-line comment per file. Use it to find a file;
  use this reference to learn what the file does.
- **[`milestones.md`](../milestones.md)** — The build order, seven milestones, and what each one delivered. What is still open:
  labelled tenders from other issuers, a scanned fixture, a run with the real tesseract.
  Also the main commands.
- **[`pitfalls.md`](../pitfalls.md)** — Ideas that look good and are not: the whole PDF to the model, a vector store, looking only
  for the five targets, trusting scores without the document checks, fuzzy labels without keyword rules,
  tuning weights to a hand-made list, and trusting a test that found nothing.
- **[`files/`](root.md)** — This file reference, one page per part of the repository: root, pipeline, interfaces,
  tests, system tests and docs. Three lines per file.
  The README's repository table links each page.

## The user guide (`docs/ui/`)

- **[`ui/guide.md`](../ui/guide.md)** — For people using the app: the page layout, the top bar (Upload PDF, Run, the
  stage line), every sidebar setting with its default, the PDF viewer, the targets strip's tiles and the messages.
  Plain language; read it before the first run.
- **[`ui/tabs.md`](../ui/tabs.md)** — The four result tabs: Sections (rows, badges, Go), JSON (flat maps, downloads),
  Checks (the review banner, what each warning code tells a reader), Debug (the candidate table's columns).
  Ends with a five-step review checklist.

## The spec (`docs/spec/`)

- **[`overview.md`](../spec/overview.md)** — §0–1: the problem statement (inputs, targets and their statuses, why the whole
  tree) and the pipeline diagram. States that every stage except the LLM's must run with the LLM disabled.
  Read it first.
- **[`data-model.md`](../spec/data-model.md)** — §2, part 1: the models stages 1–3 produce: `Line`, `TableRow`, `Table`, `Page`,
  `BoilerplateGroup`, `IndexEntry` and `ParsedDocument`, field by field.
  Includes when each field is decided (text-layer fields only after boilerplate).
- **[`results-model.md`](../spec/results-model.md)** — §2, part 2: `Candidate`, `Section`, `TargetSource` and `ExtractionResult`, field by
  field: both flat maps, the warnings, the review flag, LLM usage, the debug block.
  The shape every caller of `extract()` receives.
- **[`ingest.md`](../spec/ingest.md)** — §3–4: stage 1 (PyMuPDF settings, line merging, normalization, tables, body size,
  printed numbers), the OCR hook, and stage 2 (the boilerplate algorithm, re-admission,
  text-layer and image-only decisions).
- **[`index-candidates.md`](../spec/index-candidates.md)** — §5a–5b: how contents and annexure lists are detected and read into entries
  with applicability, and the rules for each kind of heading candidate and for bare-id titles.
  Cites the fixture pages behind each rule.
- **[`scoring.md`](../spec/scoring.md)** — §5c: every score component with its weight, the two passes, the accept and reject
  thresholds, worked examples from both fixtures with their expected breakdowns,
  and which lines end up in the LLM band.
- **[`levels-assemble.md`](../spec/levels-assemble.md)** — §6 and §8: the level rules (letters, vocabulary, dotted ids, clauses,
  sub-headings) and assembly: the tree, the end-page rule, orphans, both flat maps, unassigned pages.
  Worked against both fixtures.
- **[`llm.md`](../spec/llm.md)** — §7: the client protocol and Claude API settings, the per-line digest, the answer format,
  the essentials of the system prompt, evidence verification, confidence,
  and the results of the one real run on both fixtures.
- **[`validate-labels.md`](../spec/validate-labels.md)** — §9–10: the table of warning codes and which trigger the fallback, the
  fallback pass, the label vocabulary with its matching rules, and target resolution.
  The place to add a warning code or a label.
- **[`config-cli-ui.md`](../spec/config-cli-ui.md)** — §11–13: the settings and their precedence, the command line (flags, output, exit
  codes), and the Streamlit UI (layout, page viewer, targets strip, tabs, sidebar).
  The UI's contract: no pipeline logic.
- **[`tests-eval.md`](../spec/tests-eval.md)** — §14–16: what each test file checks, how the evaluation harness counts each metric
  and buckets errors, and the known limitations (two columns, Hindi headings,
  very long tenders, corrigenda).
