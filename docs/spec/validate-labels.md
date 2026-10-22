# Stages 9–10: validation, labels, targets (§9–10)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 9. Stage 9 — Validate (`validate.py`)

| code | check | triggers whole-doc LLM |
|---|---|---|
| `ORDER_VIOLATION` | level-1 letters not strictly increasing; annexure ids not non-decreasing in document order (compare as int tuples, within each keyword family: `Form 1` after `Annexure 5` is in order) | yes |
| `TARGET_LISTED_BUT_MISSING` | an index entry whose description maps to a **target label** is `applicable` but no section carries that label | yes |
| `EXPECTED_MISSING` | an `applicable` or `external` id from the index has no section | yes **only if ≥ 2 ids are missing**; one missing id (f2 `17`, external/empty description) is a warning only |
| `NOT_APPLICABLE_FOUND` | a `not_applicable` id was accepted as a section | yes |
| `SUSPICIOUS_LENGTH` | a level-2+ section spans > 40% of the document, or a level-1 section is < 1 page (shares its only page with the next level-1 section) | yes |
| `NO_SECTIONS` | zero accepted headings | yes |
| `UNASSIGNED_INTERIOR` | unassigned pages that are not a prefix (cover/contents) or suffix | no |
| `UNDECIDED_WITHOUT_LLM` | §5c | no |
| `PRINTED_PAGE_INCONSISTENT` | §3 | no |
| `PAGE_IMAGE_ONLY` | §4; informational | no |
| `BOOKMARK_MISMATCH` | a depth ≤ 2 bookmark has no accepted heading on its page | no |
| `LLM_PARSE_FAILED` | §7: the reply did not parse twice | no |
| `LLM_EVIDENCE_MISMATCH` | §7: an LLM decision's evidence is not on its page | no |
| `LLM_UNAVAILABLE` | §7: no answer — an API error after retries, a refusal, or a cut-off reply; the batch is rejected | no |
| `OCR_UNAVAILABLE` | §3: OCR is on, but no engine could read a page that needs it (not installed, or it failed there); the page stays image-only | no |

Target status (§10) is **not** a validation failure by itself: f1 has `scc/sor/tech_spec = not_applicable` and that is the correct answer. Only `TARGET_LISTED_BUT_MISSING` is.

Fallback (`llm/whole_doc.py`): **at most one** call per document. Input: every page's digest (`<<PAGE n>>` + first 300 non-boilerplate chars + candidate lines with flags), the index entries, and the current result with the failing checks named. Output: full list `[{page, id, title, level, evidence}]` (effort `medium`, no retry). An entry's evidence must be a line on its page (a heading that wraps matches its first line); unverifiable entries are dropped with `LLM_EVIDENCE_MISMATCH`. The kept entries replace the rule-based headings: level from the LLM, clamped to `1…max_emit_level`; kind and id from the line; label from the title (§10). Re-assemble, re-validate. If a triggering check still fails → `needs_human_review = True`. Never loop. On both fixtures the fallback must **not** fire. With the LLM disabled there is no fallback: a triggering check sets `needs_human_review = True` directly.

## 10. Stage 10 — Labels and targets (`labels.py`)

### Vocabulary
Keyword rules, not bare fuzzy matching — f2 p29 `SPECIAL CONDITIONS FOR MICRO AND SMALL ENTERPRISES` would fuzzy-match `scc` on its prefix. Acronyms match as whole uppercase words only. Phrases match word-aligned: `rapidfuzz.fuzz.ratio ≥ 90` against every window of n−1 … n+1 consecutive words of the normalized title (lower-case, `&` → `and`, punctuation → space), so the f2 p69 typo `CONDTIONS` still resolves while `UNPRICED BID` does not contain `price bid` (a substring `partial_ratio` matches it). The first label with a matching rule wins. In config (`labels.vocabulary`) a rule is terms joined by `+`, all required; `|` separates alternatives; a term in capitals is an acronym; `=` marks a phrase that must be the whole title.

```
nit            "notice inviting tender" | NIT
pqc            "pre-qualification criteria" | "prequalification criteria" | "pre qualification criteria" | PQC
               | "eligibility criteria" | "qualifying requirements" | "bidder qualification criteria" | BQC
brc            "bid rejection criteria" | BRC
atc            "agreed terms and conditions" | "agreed terms & conditions" | ATC
scc            ("special conditions" AND ("contract" OR SCC)) | "special purchase conditions" | SPC
sor            "schedule of rates" | SOR | "price schedule" | "price bid" | "bill of quantities" | BOQ
tech_spec      ("technical" AND "specification") | "tech spec" | "technical requirements" | "particular specifications"
gcc            "general conditions of contract" | GCC | "general purchase conditions" | GPC
itb            "instructions to bidders" | ITB | "instructions to tenderers"
checklist      "checklist" | "check list"
annexure_list  "list of annexures" | "annexure lists" | "tender annexures" | "annexures" (as a whole short title)
scope          "scope of work" | "scope of supply" | SOW
bank_guarantee "bank guarantee" | "surety bond" | "performance security" | EMD
declarations   "declaration" | "undertaking" | "affidavit" | "integrity pact" | "code of integrity"
other          (fallback)
```

`label_for(section)` tries the body title, then the index description, and returns the first non-`other`. f1 `Annexure 18` → body `… General Purchase Conditions (Indigenous)` → `gcc`; f2 `Annexure 20` → body `SPECIAL CONDTIONS OF CONTRACT` → `scc` (fuzzy), index `Special Conditions of Contract (SCC)` agrees.

### Target resolution
`TARGET_LABELS = ["pqc", "atc", "scc", "sor", "tech_spec"]` (config; adding a sixth is one line).

For each target label:
1. Candidates = emitted sections with that label. Pick the **shallowest level**; ties → earliest start page. f2 `tech_spec`: `Annexure 21` (L2, p79) beats `2. Technical Specification:` (L3+, p83, not emitted anyway). → `targets[label] = [start, end_page]` (inclusive), status `found`.
2. Else, if an index entry maps to the label and is `not_applicable` → `null`, status `not_applicable` (f1 `scc`, `sor`, `tech_spec`: Annexures 20/19/21 on p15 under "Annexures Not Applicable").
3. Else → `null`, status `absent`.

`targets` always contains all five keys. The UI and the CLI's default output show `targets` first.
