# Labelled tenders for the evaluation harness

Part of the project docs; start at [CLAUDE.md](../../CLAUDE.md). The metrics are SPEC §15 ([docs/spec/tests-eval.md](../../docs/spec/tests-eval.md)).

Each tender is a pair in this folder: `<name>.pdf` and `<name>.expected.json`, verified by hand against the PDF. A file without its partner is skipped with a note. Pages are 1-based **physical** everywhere.

```bash
python -m tender_sections eval eval/labelled --report eval/report.md          # the LLM as configured
python -m tender_sections eval eval/labelled --no-llm --report eval/report.md # rules alone
```

The JSON has the shape of `tests/fixtures/*.expected.json`; the harness reads four keys:

| key | what | example |
|---|---|---|
| `targets` | every target label → `[start, end]` (inclusive) or `null` | `{"pqc": [11, 13], "scc": null, …}` |
| `targets_status` | every target label → `found` / `not_applicable` / `absent` | `{"scc": "not_applicable", …}` |
| `flat_inclusive` | every section the tree should emit → `[start, end]`, a parent covering its children | `{"annexure_19": [58, 68], …}` |
| `tree_levels` | section id → level (1 top, 2 `Annexure N`, 3 `Annexure N.M` …) | `{"annexure_19": 2, …}` |

Section ids are the ones the extractor emits: the label for a labelled level-1 section (`pqc`, `annexure_list`), `annexure_19` / `annexure_2_6_1` for annexures. A level-1 id may be listed in `level1_titles` (id → heading as printed) instead of `tree_levels`. Keys starting with `_` are comments.

Before tuning any weight, add at least two tenders from an issuer other than NRL (milestone 7); the target before calling v1 done is ≥ 50 tenders across ≥ 5 issuers, ≥ 10 scanned, ≥ 5 bilingual. `eval/report.md` is generated and not committed.
