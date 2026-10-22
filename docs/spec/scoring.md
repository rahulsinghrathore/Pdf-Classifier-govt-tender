# Stage 5: scoring (§5c)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 5c. Scoring (`scoring.py`) — 0–10, integer, clamped

Positive (max 10):

| signal | pts | definition |
|---|---|---|
| `first_on_page` | +3 | first non-boilerplate line by y on the page. Not first but `y0 < 0.25` → +1 instead. |
| `emphasis` | +3 | `bold_ratio ≥ 0.5` **or** `font_size ≥ body + 1.5` **or** `caps_ratio ≥ 0.7` (≥ 4 letters). On OCR pages: bbox height or caps. |
| `pattern` | +3 | kind `letter` with caps title, kind `named`, or kind `titled` (vocabulary match **is** the pattern for unlettered headings). `letter` with Title-Case title → +2, otherwise +1. `numeric` → +1. `layout_only` → 0. |
| `listed` | +1 | `id_norm` ∈ index entries (any applicability), or the title matches a bookmark title. Cap total at 10. |

Negative:

| signal | pts | definition |
|---|---|---|
| `in_table_or_index` | −5 | `in_table` or `in_index_block`. |
| `sentence_like` | −5 | `len > 90`, or ends with `,` `;` `&` `and` `or`, or > 12 words with `caps_ratio < 0.5`. |
| `letter_reuse` | −4 | kind `letter` whose letter is already accepted at level 1 earlier (f1 p25 `D. Benefits Under…`). Second pass. |
| `unlisted_letter` | −5 | kind `letter` when the document's contents list lettered sections (`sec_*` index entries) and this letter is not among them (f1 p27 `F. Applicability of the Policy`: the contents list A–D). |
| `repeat_title` | −5 | the candidate's label (or normalized text) equals that of the most recent accepted heading, and that heading started ≤ 2 pages earlier with no other accepted heading in between. f2 p59 `SCHEDULE OF RATES` (Annexure 19 started p58); f2 p70 `Special Conditions of Contract` (Annexure 20 started p69); f2 p11 second `PRE-QUALIFICATION CRITERIA (PQC)` on the same page. Only for a candidate without an id of its own (or with the same id): a heading with a new id is a new section even when its label repeats (f1 Annexures 8, 9, 10 are all `declarations`; 15, 15.2, 15.4 all `bank_guarantee`). Second pass. |

Thresholds (config): `accept ≥ 8`, `reject ≤ 3`, else `undecided` → LLM — except `numeric` candidates while `emit_numeric_clauses` is off: they can never be emitted, so their 4–7 band is rejected by rules (breakdown `not_emitted: 0`) and costs no LLM call. With `llm.enabled = False`, `undecided → reject` with `decided_by = "disabled"` and warning `UNDECIDED_WITHOUT_LLM` listing the pages.

Worked examples (expected `score_breakdown`):

```
f1 p5  "B. PRE-QUALIFICATION CRITERIA (PQC)"   first+3 emph+3 pattern+3 listed+1              = 10 accept
f1 p14 "D. TENDER ANNEXURES"                   first+3 emph+3 pattern+3 listed+1              = 10 accept  (above the table → no −5)
f1 p14 "Annexure 1" (list row)                 top25+1 pattern+3 listed+1 table−5             =  0 reject
f1 p3  "Annexure 8" (checklist cell, bold)     emph+3 pattern+3 listed+1 table−5              =  2 reject
f1 p16 "Annexure 1"                            first+3 emph+3 pattern+3 listed+1              = 10 accept  (first only after Job Name lines stripped)
f1 p17 "Information for transporter / goods…"  first+3 emph+3                                 =  6 undecided → LLM (reject when disabled — correct)
f1 p25 "D. Benefits Under The Public Procure…" top25+1 emph+3 pattern+2 listed+1 sentence−5 letter_reuse−4 = 0 reject
f1 p52 "Annexure 18"                           first+3 emph+3 pattern+3 listed+1              = 10 accept  (first by y-sort, not by block order)
f1 p59 "22 Acceptance of bid & Upon accept…"   first+3 pattern+1 table−5 sentence−5           =  0 reject  (title cell merges with its body cell: not bold, 117 chars)

f2 p2  "NOTICE INVITING TENDER"                first+3 emph+3 pattern(titled)+3               =  9 accept  (10pt bold caps; no letter prefix)
f2 p11 "PRE-QUALIFICATION CRITERIA (PQC)" y.12 first+3 emph+3 pattern+3                       =  9 accept
f2 p11 "PRE-QUALIFICATION CRITERIA (PQC)" y.19 top25+1 emph+3 pattern+3 repeat−5              =  2 reject
f2 p1  "PART–I: UNPRICED BID"                  emph+3 pattern(named)+3                        =  6 undecided → LLM (cover label; reject when disabled — correct)
f2 p17 "LIST OF ANNEXURES"                     first+3 emph+3 pattern+3                       =  9 accept  (title above the index table)
f2 p29 "SPECIAL CONDITIONS FOR MICRO AND SMA…" not a candidate: not first on its page, no label (no scc token match) → rejected
f2 p58 "Annexure 19" → title "SCHEDULE OF RATES" first+3 emph+3 pattern+3 listed+1            = 10 accept
f2 p59 "SCHEDULE OF RATES"                     first+3 emph+3 pattern+3 table−5 repeat−5      =  0 reject  (the title row of a ruled table)
f2 p70 "Special Conditions of Contract"        emph+3 pattern+3 repeat−5                      =  1 reject
f2 p74 "18. Schedule of Rates"                 emph+3 pattern(numeric)+1                      =  4 reject (not emitted); level ≥ 3 regardless → cannot win the sor target
f2 p83 "2. Technical Specification:"           top25+1 emph+3 pattern+1                       =  5 reject (not emitted); level ≥ 3 regardless → cannot win the tech_spec target
```

Target: **both fixtures reach ground truth with the LLM disabled.** Undecided candidates on the fixtures are exactly: f1 p17; f2 p1 (`(Domestic Open Tender)`, `PART–I: UNPRICED BID`), p29 / p31 / p32 (Annexure 3's lettered sub-headings A.–C., E.–G.), p70 / p80 (cover-page letterhead `REFINERY` and the tagline `A GOVERNMENT OF INDIA UNDERTAKING`, which maps to `declarations`) — all correctly rejected when the LLM is off. If a change pushes any `must_accept` heading into 4–7, that is a tuning regression — fix the weights or the signal, do not edit the expected JSON.
