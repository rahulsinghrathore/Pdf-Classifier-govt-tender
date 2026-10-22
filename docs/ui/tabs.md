# Using the app: the result tabs

Part of the user guide; previous page: [the page and its controls](guide.md). The tabs appear on the right after a **Run**.

## Sections — the tender's table of contents, as found

Each top-level section is a fold-out row (click ▸ to open it), titled with its heading and page range. Inside, one row per section and sub-section, indented by depth:

| Part of a row | Meaning |
|---|---|
| Heading | As printed (`B. PRE-QUALIFICATION CRITERIA (PQC)`), or the annexure number with the title found below it (`Annexure 19 — SCHEDULE OF RATES`). |
| Blue badge (`sor`, `scc` …) | The section's label: what kind of section it is. Unlabelled sections have none. |
| `p58–68` | First and last page, including its sub-sections. |
| Confidence badge | Green 0.85 or more: sure. Orange 0.60–0.85: worth a look. Red below 0.60: check it. |
| Violet **LLM** badge | Claude decided this heading (the rules were unsure). Its confidence is never above 0.85. |
| **Go** | Shows the section's first page in the viewer, heading framed in red. |

*Pages in no section* at the bottom lists pages before the first section (cover, contents). That is normal at the start of a tender; inside it, see the Checks tab.

## JSON — the result as data

| Part | What it is |
|---|---|
| First box | The targets and their status: the answer the business asked for. |
| **Flat map** *Inclusive / Exclusive* | Every section with its page range. *Inclusive*: a parent covers its children (`annexure_list` = 14–67). *Exclusive*: a parent stops where its first child starts (14–15). |
| Third box | The complete result (folded): tree, warnings, review flag, LLM usage. |
| **targets.json** / **sections.json** / **full.json** | Downloads, named after your file: the targets only; the tree with both flat maps; everything (with debug data only while *Show debug* is on). |

## Checks — can this result be trusted?

- **Red banner** *Needs human review*: a document-level check failed (sections out of order, a listed target missing, a "Not Applicable" section found anyway, a section of an odd length, or no sections at all). Read the warnings below before using the result. **Green banner**: no check failed.
- **Listed but not found**: ids the tender's own annexure list names that have no section (e.g. `annexure_17`).
- **Not Applicable but found**: ids the tender calls Not Applicable that were found anyway.
- **Warnings**, one fold-out per code with a count; each line names its page:

| Code | What it tells you |
|---|---|
| `UNDECIDED_WITHOUT_LLM` | The LLM was off, so unsure lines were rejected; the pages are listed. Re-run with the LLM on if a section seems missing there. |
| `EXPECTED_MISSING` | A listed annexure has no section. One is usually harmless; two or more trigger review. |
| `PAGE_IMAGE_ONLY` | A page is a picture without text (a drawing or scan); it counts as part of the section around it. |
| `LLM_UNAVAILABLE` / `LLM_PARSE_FAILED` | Claude could not answer (network, refusal, invalid reply); unsure lines were rejected. |
| `LLM_EVIDENCE_MISMATCH` | Claude's quote was not on the page, so its answer was thrown away. |
| `ORDER_VIOLATION`, `TARGET_LISTED_BUT_MISSING`, `NOT_APPLICABLE_FOUND`, `SUSPICIOUS_LENGTH`, `NO_SECTIONS` | The checks behind the red banner. |

The full list of codes: [SPEC §9](../spec/validate-labels.md).

## Debug — the evidence behind the result (only with *Show debug*)

- **Candidates**: every line that looked like a heading. Columns: `page`, `text`; `kind` (letter, named, numeric, titled, layout_only); `score` and its `breakdown` (which rules added or took points); `decision` (accept, reject, undecided); `decided_by` (rules, llm, or disabled = rejected because the LLM was off or failed); `level`; `label`. Look here when a section is missing or wrong.
- **Boilerplate lines**: running headers and footers ignored on each page.
- **Index entries**: what the tender's own contents / annexure lists say, with *applicable*, *not_applicable* or *external*.
- **LLM transcripts**: every Claude call, exactly as sent and answered.

## A typical review in five steps

1. Upload the tender; decide on the LLM toggle; press **Run**.
2. Read the targets strip: green tiles give page ranges, grey ones should name the page that says Not Applicable.
3. Click each tile and check, in the viewer, that the red frame sits on the right heading.
4. Open **Checks**: a red banner or an `EXPECTED_MISSING` warning tells you where to look.
5. Download **targets.json** (or **full.json** to keep everything).
