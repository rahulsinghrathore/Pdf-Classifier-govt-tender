# Files: test support, fixtures and stage tests (`tests/`)

File reference: [root](root.md) · [pipeline](pipeline.md) · [interfaces](interfaces.md) · **tests** · [system tests](tests-system.md) · [docs](docs.md). Start at [README.md](../../README.md).

## Support

- **[`conftest.py`](../../tests/conftest.py)** — Runs around every test: switches the LLM off (`TENDER_LLM__ENABLED=false`) and makes
  building the real Anthropic client fail, so no test can reach the network (CLAUDE.md hard rule 16).
  Keeps the real constructor aside for the one test that checks it against a stubbed SDK.
- **[`helpers.py`](../../tests/helpers.py)** — Access to the two fixtures: their PDFs (tests skip while one is absent), their expected JSON,
  and cached outputs of stages 1–5 and of `extract()` with the LLM off. Also `anchor`, which fails a trap test whose
  text matches nothing on its page, and the safety net's one known exception (f2 p1).
- **[`fakes.py`](../../tests/fakes.py)** — Scripted stand-ins: `verdict` answers every adjudication request with one decision, and
  `shown` lists the lines a request showed. `FakeOCREngine` and `printed` play tesseract, with boxed words.
  Nothing in it touches the network or a real engine.
- **[`pdfgen.py`](../../tests/pdfgen.py)** — Builds tiny PDFs in memory: text at given positions and sizes, bold, images, ruled tables,
  vector strokes, headers, footers, landscape pages. Lets every ingest and boilerplate rule be tested
  without the fixture PDFs.
- **[`synthetic.py`](../../tests/synthetic.py)** — Builds synthetic heading candidates (`heading(...)`) for the pure-function stages:
  levels, assemble and validate. No PDF is involved.
  Lets the tree and end-page rules be tested on a few lines of setup.

## Fixtures (`tests/fixtures/`)

- **`nrl_pur1011567.pdf` + `.expected.json`** — Fixture 1: an NRL GeM supply tender, 67 pages, lettered sections `A.`–`D.`;
  SCC, SOR and technical specifications are listed as Not Applicable on p15. The JSON is the hand-verified truth:
  targets, both flat maps, levels, traps, index pages, boilerplate lines. Never edited to make a test pass.
- **`nrl_pur1011848.pdf` + `.expected.json`** — Fixture 2: an NRL works tender, 85 pages, unlettered top-level sections; SOR,
  SCC and technical specifications are Annexures 19, 20 and 21. Quirks: running section titles, the SOR's own page
  numbers, image-only drawings on pp84–85, Annexure 17 listed but absent.
- **`A_179e95f1-…YuvJyoti 1.pdf`** — The original download of fixture 1, byte-identical to `nrl_pur1011567.pdf`.
  No test reads it, and the harness skips it because it has no `.expected.json`.
  Safe to delete.

## Stage tests

- **[`test_config.py`](../../tests/test_config.py)** — `config.yaml` equals the code defaults; environment variables override the YAML;
  unknown keys and missing files are errors. Also the heading patterns: named ids match, and lower-case letters
  (`a) …`) never count as lettered headings.
- **[`test_ingest.py`](../../tests/test_ingest.py)** — Stage 1: y-order over stream order (f1 p52), baseline merges (f1 p25), landscape and
  rotated pages, table flags, a page frame that is not a table, body font sizes, printed page numbers (f2's
  `SOR Page X of 10` ignored), and nothing printed on stdout.
- **[`test_boilerplate.py`](../../tests/test_boilerplate.py)** — Stage 2: band text repeated on 3 or more pages is stripped, `Annexure 3` is not,
  spacing variants are one group, vocabulary running titles go too. Each fixture's expected boilerplate lines are
  flagged, its first content lines found (f1 pp41–42), and f2 pp84–85 are image-only.
- **[`test_index_pages.py`](../../tests/test_index_pages.py)** — Stage 3: annexure tables and contents lists become entries; too few ids, long
  descriptions and clause tables (f2's ATC) do not; serial-number columns are skipped. Not Applicable carries to the
  next page, empty descriptions are external (f2 Annexure 17); both fixtures' index pages and counts.
- **[`test_candidates.py`](../../tests/test_candidates.py)** — Stage 4: the five candidate kinds, and what is never one (list items, captions,
  vocabulary words in plain text). Bare ids take their titles from the lines below or the index:
  f2's `annexure_titles_from_body`, and f1's Annexure 18 → `gcc`.
- **[`test_scoring.py`](../../tests/test_scoring.py)** — Stage 5: repeat and letter-reuse penalties, the spec's worked examples, both
  fixtures' LLM band. Every `must_accept` trap scores 8 or more, every `must_reject_or_demote` trap 7 or less; an
  unsure trap, if accepted, still lands at level 3 or deeper, except f2 p1 `PART–I`.
- **[`test_levels.py`](../../tests/test_levels.py)** — Stage 6 on synthetic headings: lettered and vocabulary top-level sections, dotted
  annexures, orphans keeping their level, numbered clauses, sub-headings below the open heading. Also the bare-id
  title line being consumed, and which headings are emitted.
- **[`test_assemble.py`](../../tests/test_assemble.py)** — Stage 8 on synthetic headings: nested inclusive and exclusive ranges, a heading
  that starts mid-page, the orphan rule, two headings that cannot both open one page, unassigned pages,
  unique section ids.
- **[`test_validate.py`](../../tests/test_validate.py)** — Stage 9: a synthetic case for each check, including order within each id family
  (`Form 1` after `Annexure 5` is in order), and one missing listed id warning where two fail the document.
  A clean document gets no warnings.
- **[`test_labels.py`](../../tests/test_labels.py)** — Stage 10: the vocabulary (`CONDTIONS` → `scc`, the MSE line → not `scc`), the first
  matching label wins, the index description as fallback. Targets: the shallowest section wins, then the earliest;
  `not_applicable` versus `absent`; the source behind each answer.
