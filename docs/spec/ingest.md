# Stages 1–2: ingest and boilerplate (§3–4)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 3. Stage 1 — Ingest (`ingest.py`)

Use `import pymupdf` (not the deprecated `fitz` alias).

1. `doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")`.
2. `doc.get_toc()` → if non-empty, keep as `bookmarks` (a strong prior; §5c bonus). Empty on both fixtures.
3. For every page:
   - `page.get_text("dict", sort=True)` → spans → raw lines. **Do not trust block order without `sort=True`**: on fixture 1, page 52 returns `"Definition:"` before `"Annexure 18"` and page 15 returns the note before the table.
   - Text: ligatures expanded (`TEXT_PRESERVE_LIGATURES` off, so `speciﬁcation` matches the vocabulary), NFKC, curly quotes straightened, soft hyphens and zero-width characters dropped. Lines that are not horizontal on screen (`|dir.y| > 0.05`: stamps, watermarks) are dropped. On a `/Rotate` page `get_text()` reports boxes and directions on the unrotated page, while `page.rect` and `find_tables()` use the displayed one: every line is mapped through `page.rotation_matrix` first, so landscape content that reads upright on screen is kept and placed where it is shown.
   - **Merge same-baseline fragments**: two raw lines whose vertical centres differ by less than `0.3 × font_size` are one logical line; join with a space, ordered by x0. This turns `"D."` + `"Benefits Under…"` (f1 p25), `"Job Name"` + `":"` + `"Supply of FLP…"` (f1 p16), and `"22"` + `"Acceptance of bid &"` (f1 p59) into single lines.
   - Normalize coordinates to 0..1 by page width/height (f2 p84 is landscape A3 — never assume portrait).
   - `bold_ratio` from span flags (`flags & 16`) or font name containing `Bold`.
   - `tables = page.find_tables()`, ignoring tables of fewer than 2 rows: f2 pp70–78 sit inside a page border that `find_tables()` reports as a one-row table, which would put every line "in a table". Rows and cells are kept for §5a. A line is `in_table` if its bbox centre is inside any table bbox.
   - `body_font_size` = character-weighted mode of `font_size` (bucketed to 0.5 pt, ties to the smaller size), so a page of one-word 8 pt cells beside long 10 pt paragraphs has a 10 pt body. A page with fewer than 200 non-space characters takes the **document's** body size instead: f2 pp58/69/79 hold only a 36 pt title, which could otherwise never look larger than the body. Fallback 10.0; recomputed without boilerplate after stage 2.
   - `image_count` (`get_image_info()`) and `drawing_count` (`get_drawings()`) feed the image-only decision (§4). `pymupdf.no_recommend_layout()` is called once, so `find_tables()` prints nothing on stdout (the CLI's JSON goes there).
   - `printed_number`: in the top 10% / bottom 10% bands match `r"Page\s+(\d+)\s+of\s+(\d+)"` and `r"^-?\s*(\d{1,4})\s*-?$"`. **Keep only matches whose `of N` equals `len(doc)`** (or that have no `of N`). Fixture 2 pages 59–68 also carry `SOR Page 1 of 10`…`10 of 10` — a nested numbering that must be ignored.
4. `printed_page_offset` = the constant `printed − physical` if identical on ≥80% of pages that have one, else `None` + warning `PRINTED_PAGE_INCONSISTENT`.

### OCR hook (`ocr.py`)
Off by default (`ocr.enabled`). The decision *whether* a page needs OCR is made in stage 2 (below), not here. `apply_ocr` renders each such page at `ocr.dpi` and hands it to an `OCREngine` (`words(image) -> list[OCRWord]`: text, pixel box, line id); `ocr_page(pix, page, engine) -> list[Line]` turns the words into lines through the same same-baseline merge as text-layer lines.
- OCR lines get `font_size` = the line's height in points and `bold_ratio = 0.0`, so emphasis comes from height and capitals with no scoring change. The page is tagged `ocr` and stays `is_image_only`.
- A line the text layer already has (a running footer) is not added twice; boilerplate is then found again over all lines.
- The engine is tesseract (`pytesseract.image_to_data` in `ocr.languages`, words below `ocr.min_word_confidence` dropped): `pip install -e ".[ocr]"` and the tesseract program. `paddle` is not implemented. `extract(ocr=…)` takes another engine (tests: a scripted one).
- No engine that can run → warning `OCR_UNAVAILABLE` and the pages stay image-only; an engine error on one page → the same warning for that page.

**Important scoping fact:** image-only pages *inside* a section (fixture 2 pp84–85, drawings at the end of Technical Specifications) do not need OCR for the page ranges to be right — the end-page rule covers them. OCR is only required when a section *starts* on an image-only page. So OCR is a milestone-7 concern, not a v1 blocker.

## 4. Stage 2 — Boilerplate (`boilerplate.py`)

Goal: remove running headers/footers so that "first line on the page" means the first *content* line.

Algorithm:
1. Consider only lines whose `y0 < 0.12` (top band) or `y1 > 0.90` (bottom band).
2. Key = `(band, text.lower() with all whitespace removed)`. Spacing is ignored because fragment joins vary: f1 pp41–42 read `NRL Tender No. : PUR1011567`, the other 23 pages `NRL Tender No.: PUR1011567`. Otherwise **exact text**, not digit-normalized (digit normalization would collapse `Annexure 2` / `Annexure 3` / … into one key and strip real headings).
3. Additionally key page-number patterns by regex: `Page \d+ of \d+`, `^\d{1,4}$`, `^- \d+ -$`, `Sys\. Gen\.` → always boilerplate when in a band. This also removes `SOR Page X of 10`.
4. A key is boilerplate if it occurs on **≥ 3 distinct pages** (config `boilerplate.min_pages`). Not a percentage: on fixture 1 the header changes at page 14, so `NRL Tender Ref. No…` is on 13/67 pages and the `Job Name / NRL Tender No. / PUR1011567` lines on ~27/67; on fixture 2 `SPECIAL CONDITIONS OF CONTRACT` is on 8/85 and `Technical Tender Document` on 4/85. A 50% rule misses all of them.
5. **Exempt structural headings**: never mark a line as boilerplate if it matches the `letter` or `named` regex (§5a). **Do not exempt `titled` (vocabulary) lines**: `SPECIAL CONDITIONS OF CONTRACT` as a running header on fixture 2 pp71–78 must be stripped, otherwise each of those pages would present a 9-point "heading".
6. **Re-admission rule** (handles the document whose section has *only* a running-title heading): after stage 5 scoring, if a stripped boilerplate group matches a vocabulary label (§10) and no accepted section carries that label, re-admit the group's **first occurrence** as a `titled` candidate and score it normally. If it opens its page, the line that was first there no longer is. On fixture 2 this never fires (Annexure 20 / 21 carry the labels), which is the test: re-admission must be a no-op there.
7. Mark `line.is_boilerplate = True`. Do not delete lines; downstream filters on the flag (the UI shows them in Debug).

Then decide text-layer status per page:
- `has_text_layer = len(non-boilerplate text) ≥ 20 chars`. Fixture 2 pp84–85 have 42 chars of footer each and nothing else → **no** text layer. (A naive `len(page.get_text()) ≥ 20` gets this wrong.)
- `is_image_only = not has_text_layer and (page has ≥1 image or ≥ 50 vector paths)`: a CAD drawing may be vector graphics. (f2 pp84–85 have one raster image each.) The three fields are `None` until this stage decides them.
- `needs_ocr = is_image_only and config.ocr.enabled`. If OCR is disabled, warning `PAGE_IMAGE_ONLY` (informational) — the page will fall inside whichever section surrounds it.

Fixture checks (`test_boilerplate.py`): the `boilerplate_lines_expected` strings of each fixture are flagged; `"Annexure 3"` (f1: pages 3, 14, 24) is **not** flagged; f2 `image_only_pages == [84, 85]`.
