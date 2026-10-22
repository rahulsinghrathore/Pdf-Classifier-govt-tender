# Overview: the problem and the pipeline (§0–1)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 0. Problem statement

Input: one government tender PDF (digital or scanned, 10–500 pages, any issuer).

Output:
1. **`targets`** — the five labels the business asked for, each with `[start, end]` or `null`: `pqc`, `atc`, `scc`, `sor`, `tech_spec`. Plus a status per label: `found` / `not_applicable` (the document itself says so) / `absent`.
2. **The full section tree** with page ranges (flat maps in two conventions) — because the five targets live at *different levels* in different tenders (top-level sections in one, annexures in another), and because the next request will be a sixth label.

Framing: **hierarchical document segmentation**. Find the pages where sections *start*; compute where they *end* in code; map titles to labels; resolve each target to the shallowest matching section. The LLM is a judge for ambiguous heading candidates, never the primary parser and never the thing that computes page ranges.

## 1. Pipeline overview

```
PDF bytes
  │
  ├─ 1 ingest        PyMuPDF → pages → logical lines (y-sorted, baseline-merged) with font/bold/bbox/in_table
  │                   bookmarks; printed page numbers (only the series whose "of N" == page count)
  │
  ├─ 2 boilerplate   strip running headers/footers (exact-text repeats, spacing ignored, in top/bottom band on ≥3 pages)
  │                   THEN decide image-only / needs-OCR pages (footer text alone is not a text layer); OCR them if enabled
  │
  ├─ 3 index blocks  detect contents / annexure-list blocks → expected_ids{applicable|not_applicable|external} + descriptions
  │
  ├─ 4 candidates    letter / named / numeric / titled(vocabulary) / layout_only lines; bare-id headings pick up their title
  │
  ├─ 5 scoring       0–10 per candidate (weights in config). ≥8 accept · ≤3 reject · 4–7 → LLM (numbered clauses that are not emitted: reject)
  │
  ├─ 6 levels        1 = lettered or vocabulary-titled top sections; 2+ = Annexure N / N.M / N.M.K; numeric clauses ≥3
  │
  ├─ 7 llm           adjudicate the 4–7 band (per-page digest in, {decision, evidence} out, evidence verified; levels stay §6's)
  │
  ├─ 8 assemble      sort by (page, y) → tree → end pages (next heading outside the subtree) → flat_inclusive / flat_exclusive → unassigned pages
  │
  ├─ 9 validate      ordering · expected vs found · not-applicable present · suspicious lengths
  │                   hard failure → ONE whole-document LLM pass → re-assemble → re-validate → human_review flag
  │
  └─ 10 labels       title/index-description → canonical label; resolve the five targets → ExtractionResult
```

Stages 1–6 and 8–10 are deterministic and must run with the LLM disabled. Both fixtures must reach ground truth with the LLM disabled. Stage 7 and the fallback in 9 are the only LLM touch points.
