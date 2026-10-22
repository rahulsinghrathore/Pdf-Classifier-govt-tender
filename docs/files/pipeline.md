# Files: the pipeline (`src/tender_sections/`)

File reference: [root](root.md) · **pipeline** · [interfaces](interfaces.md) · [tests](tests.md) · [system tests](tests-system.md) · [docs](docs.md). Start at [README.md](../../README.md).

The stage modules are deterministic: none imports `tender_sections.llm` (CLAUDE.md hard rule 3). Stage numbers are the spec's; the LLM (stage 7) runs between scoring and levels.

- **[`__init__.py`](../../src/tender_sections/__init__.py)** — The public entry point: `extract(pdf, settings, *, llm, ocr, debug, on_stage)`
  runs the stages in order and returns the `ExtractionResult`, building the Anthropic client only when it is needed.
  Also re-admits a stripped running title that alone carries a label (SPEC §4), and exports the public names.
- **[`config.py`](../../src/tender_sections/config.py)** — Every tunable in one pydantic `Settings` object, a section per stage: weights,
  thresholds, bands, regexes, the label vocabulary, the target labels, LLM and OCR options (hard rule 14).
  Read from code defaults, a YAML file (`load_settings`) and `TENDER_<SECTION>__<KEY>` variables; unknown keys fail.
- **[`models.py`](../../src/tender_sections/models.py)** — The pydantic data model every stage shares: `Line`, `Page`, `Table`, `IndexEntry`,
  `ParsedDocument`, `Candidate`, `Section`, `TargetSource`, `ExtractionResult`, and `Warning` with its stable codes.
  Pages are 1-based physical everywhere; line coordinates are normalized to 0..1 of the page.
- **[`headings.py`](../../src/tender_sections/headings.py)** — The structural heading patterns stages 2–4 share: `letter` (`B. …`),
  `named` (`Annexure 2.6.1`, `PART–I`) and `numeric` (`2.6 …`). `match_heading` returns the kind, id and title;
  `is_structural` marks lines that are never boilerplate; `named_id_norm` builds ids such as `annexure_2_6_1`.
- **[`ingest.py`](../../src/tender_sections/ingest.py)** — Stage 1: PDF → pages of logical lines, with PyMuPDF. Lines are sorted by y and
  same-baseline fragments merged (hard rule 5); text is normalized; rotated pages are mapped to the displayed frame.
  Also finds ruled tables, bookmarks, body font sizes and printed page numbers (only a series whose `of N` is the page count).
- **[`boilerplate.py`](../../src/tender_sections/boilerplate.py)** — Stage 2: running headers and footers, i.e. text repeated exactly (spacing
  ignored) in the top or bottom band on 3 or more pages, plus page-number lines; letter and named headings are exempt.
  Then the text layer is decided per page, after stripping, so a page holding only a footer is image-only.
- **[`ocr.py`](../../src/tender_sections/ocr.py)** — Optional OCR for image-only pages, off by default: the `OCREngine` interface, a tesseract
  engine and `apply_ocr`. Words become lines through the same merge as text; a line the text layer has is not doubled.
  No engine, or a failure on a page → warning `OCR_UNAVAILABLE`, and the page stays image-only.
- **[`index_pages.py`](../../src/tender_sections/index_pages.py)** — Stage 3: the tender's contents and annexure lists, read from ruled tables or
  from lines, become `IndexEntry`s with a description and an applicability: applicable, not applicable or external.
  Rows are flagged `in_index_block` (−5 later), the title is not; "Not Applicable" covers the rest of its page and the next.
- **[`candidates.py`](../../src/tender_sections/candidates.py)** — Stage 4: heading candidates of five kinds: `letter`, `named`, `numeric`,
  `titled` (a short emphasized line that maps to the vocabulary) and `layout_only` (an emphasized first line).
  A bare `Annexure 19` takes its title from the largest emphasized lines below it, else from the index description.
- **[`scoring.py`](../../src/tender_sections/scoring.py)** — Stage 5: a 0–10 score per candidate with a breakdown: position, emphasis, pattern,
  index listing, table and sentence penalties, then letter reuse and repeated titles, in document order.
  8 or more accept, 3 or less reject, 4–7 undecided (the LLM's band); `reject_undecided` serves the LLM being off.
- **[`levels.py`](../../src/tender_sections/levels.py)** — Stage 6: levels of accepted headings. Level 1: capital letters, top-level vocabulary
  titles, Section / Part / Chapter; `Annexure N.M`: 2 + dots; numbered clauses: dots + 3; others: below the open heading.
  `emitted` keeps what the tree shows: headings no deeper than `max_emit_level`, numbered clauses left out.
- **[`assemble.py`](../../src/tender_sections/assemble.py)** — Stage 8: the tree and every page range. A section ends where the next heading
  outside its own subtree starts (that same page if it starts mid-page); an orphan `Annexure 7.2` hangs under level 1.
  Emits the inclusive and exclusive flat maps, unique section ids, and the pages no top-level section covers.
- **[`validate.py`](../../src/tender_sections/validate.py)** — Stage 9: document checks with stable codes: order, a listed target missing,
  listed ids missing, Not Applicable found, odd lengths, no sections, and more. A triggering check calls the one
  whole-document LLM pass, or sets `needs_human_review` with the LLM off; one missing listed id is only a warning.
- **[`labels.py`](../../src/tender_sections/labels.py)** — Stage 10: title → label by keyword rules (acronyms, required terms, whole titles),
  then word-aligned fuzzy matching (ratio ≥ 90), so the typo `CONDTIONS` still reads as the SCC. `resolve_targets` picks
  the shallowest section per target, earliest on a tie, else reads the index for `not_applicable` or `absent`.
