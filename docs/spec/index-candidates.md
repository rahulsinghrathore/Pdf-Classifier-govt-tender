# Stages 3–4: index blocks and candidates (§5a–5b)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 5a. Index blocks (`index_pages.py`)
The table route comes first: `find_tables()` rows whose first non-empty cell (after an optional serial number: `1 | Annexure 1 | …`) is a **listed id** give `(Number, Short Description)` directly on both fixtures. Named ids (`Annexure 19`, `Part II`) are listed ids anywhere; bare letters (`A`, `B.`) only on a page with a contents-like title, because clause tables use them too (f2 p15: the ATC table lists clauses A–Q). A page is an index page when its tables give ≥ 5 listed rows (≥ 4 when a non-table line fully matches `(table of contents|contents|index|list of annexures?|annexures? lists?):?` — f1 p2 `Contents:`) and a median description of ≤ 100 chars; each such table is a block. Otherwise the line route: ≥ 5 short (≤ 60 chars) listed-id lines on one page sharing a left edge (`x0` within 0.03), interleaved description lines allowed.

Outputs:
- `line.in_index_block = True` for lines inside the block (**not** for the page's own title above it — f1 p14 `D. TENDER ANNEXURES` and f2 p17 `LIST OF ANNEXURES` must not be penalized).
- `IndexEntry` list. Applicability: `not_applicable` if the entry lies below the first non-table line matching `not applicable` on its page, or on the next page when that is an index page too (f1 p14 y≈0.73 governs the rest of p14 and all of p15; f2 p17 y≈0.82 governs the rest of p17 and all of p18). `external` if the description is empty or a placeholder (`None`, `Nil`, `N/A`, `-`: f2 `Annexure 17` is listed with the description `None` and is absent from the body), or matches `\b(website|link|available at|refer .* portal|separately|to be downloaded)\b` (word-bounded: "Purchase Preference *linked* with Local Content" is not a link). Otherwise `applicable`.
- Descriptions are kept: they are the second source of a section's title (§5b) and label (§10).

Fixture checks: f1 `index_pages == [2, 14, 15]`, 26 applicable / 22 not-applicable; f2 `index_pages == [17, 18]`, 31 applicable + 1 external (`17`) / 19 not-applicable.

## 5b. Candidate generation (`candidates.py`)
A non-boilerplate line becomes a candidate if at least one holds:

| kind | regex / rule (on the logical line; keywords match in any case, letters and roman numerals in capitals only) | notes |
|---|---|---|
| `letter` | `^([A-Z])[.)]\s+(.{3,120})$` | id = letter. Capitals only: `a) …` is a list item. |
| `named` | `^(?i:(annexure|appendix|schedule|section|part|chapter|form|format|exhibit))\s*[-–:]?\s*([IVXLC]+\|\d+(?:\.\d+)*[A-Za-z]?)\b[\s:–-]*(.*)$` | id = roman/decimal. Roman numerals in capitals, so `Section Civil Works` is not section "Civil". |
| `numeric` | `^(\d+(?:\.\d+)*)[.)]?\s*(\(?[A-Z]\)?)?\s+(.{3,120})$` | clause numbering. Always level ≥ 3. |
| `titled` | no id; `len ≤ 90`, ≤ 10 words, **emphasized** (as in §5c), and the text maps to a vocabulary label (§10) | f2 `NOTICE INVITING TENDER`, `PRE-QUALIFICATION CRITERIA (PQC)`, `BID REJECTION CRITERIA`, `LIST OF ANNEXURES`; f2 p59 `SCHEDULE OF RATES`. |
| `layout_only` | none of the above, but `font_size ≥ body + 1.5` or `bold_ratio ≥ 0.6`, `len ≤ 90`, and `first_on_page` | f1 p17 `Information for transporter / goods carrier`. |

A `named` match **not at the start of the line** (`… as per Annexure 8 …`) is not a candidate at all. Neither are: lower-case list items (`^\(?([a-z]|[ivx]{1,4})[.)]\s` — f2 p14 `d) Schedule of Rates / Price Schedule / Price Basis`); a contents-like caption that maps to no label (f1 p2 `Contents:` — front matter); and vocabulary words in unemphasized text (f2 p7 `clause 7.2 of GCC).`), which could never reach accept anyway (at most first+3 pattern+3 listed+1 = 7).

**Title lookup for bare ids.** When a `letter`/`named` candidate has an empty title (f2 `Annexure 19`, `Annexure 20`, `Annexure 21`, `Annexure 1`; f1 every annexure), fill `title` from, in order:
1. `lines_below`: emphasized (`bold_ratio ≥ 0.5` or `font_size ≥ body + 1.5`) non-boilerplate lines in the top 50% of the same page below the id, skipping lines that end in `,` or `;` (salutations and addresses: `To, Numaligarh Refinery Limited,`); take the group with the **largest font size**, join consecutive lines of that size. f2 p58 → `SCHEDULE OF RATES` (36 pt); f2 p69 → `SPECIAL CONDTIONS OF` + `CONTRACT` → `SPECIAL CONDTIONS OF CONTRACT` (typo preserved); f2 p19 → `Instructions To Bidders In Brief`; f1 p52 → all three consecutive 12 pt lines, `NUMALIGARH REFINERY LIMITED General Purchase Conditions (Indigenous) - 2024 (Effective from 09.09.2024)`.
2. `index`: the `IndexEntry.description` for the same `id_norm`.
3. `none`.
Record `title_source`. Label mapping (§10) tries the body title first, then the index description.
