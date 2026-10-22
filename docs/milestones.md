# Build order (one milestone per PR; do not skip ahead)

Part of the project docs; start at [CLAUDE.md](../CLAUDE.md).

| # | Milestone | Status |
|---|---|---|
| 1 | Skeleton + ingest + boilerplate | done |
| 2 | Index blocks + candidates + scoring | done |
| 3 | Levels + assemble + validate + labels; end-to-end contract | done |
| 4 | LLM adjudication + whole-document fallback | done |
| 5 | CLI | done |
| 6 | Streamlit UI | done |
| 7 | Eval harness + OCR | code done; waits for labelled tenders and a scanned fixture |

1. **Skeleton + ingest + boilerplate.** `models.py`, `config.py`, `ingest.py`, `boilerplate.py`. Tests: page counts; f1 p52 first line by y is `Annexure 18`; f1 p25 merged `D. Benefits…` line; each fixture's `boilerplate_lines_expected` flagged, `Annexure 3` not; f2 `image_only_pages == [84, 85]`; f2 `SOR Page X of 10` ignored for printed numbering.
2. **Index blocks + candidates + scoring.** Tests: index pages and applicability counts for both fixtures (f2 `17` is `external`); bare-id title lookup reproduces f2 `annexure_titles_from_body`; every `traps.must_accept` ≥ 8; every `traps.must_reject_or_demote` ≤ 7. Print the score-breakdown table for both fixtures and compare with SPEC §5c.
3. **Levels + assemble + validate + labels.** Pure-function tests with synthetic headings; vocabulary tests (typo `CONDTIONS` → `scc`; f2 p29 MSE line → not `scc`); target resolution picks shallowest. Then `test_e2e_fixture.py` for both fixtures with the LLM disabled: `targets`, `targets_status`, both flat maps and the levels must match exactly; the fallback must not fire; undecided pages are exactly f1 `{17}`, f2 `{1, 29, 31, 32, 70, 80}` (numbered clauses skip the LLM while they are not emitted; see SPEC §5c).
4. **LLM.** `client.py` (`AnthropicClient` + `FakeLLMClient`), `adjudicate.py`, `whole_doc.py`, evidence verification, usage accounting. Tests only with the fake client, including an evidence-mismatch case. Then run both fixtures with the real LLM once, by hand, and confirm the undecided candidates are rejected (f1 p17; f2 p1, p29, p31, p32, p70, p80) — f2 p1 `PART–I: UNPRICED BID` above all, since nothing but the model stops it. If the model accepts any, fix the prompt, not the scorer. The fake-client tests repeat the trap safety net of `test_scoring.py` with its one exception. *Done:* the real run (Claude Sonnet 5.5, `low`) rejected all 13, PART–I at 0.95, and reproduced both ground truths; SPEC §7 has the details.
5. **CLI** per SPEC §12. *Done:* `extract` prints both fixtures' expected targets; `--full`, `--debug` (candidate table on stderr), exit 0 / 2 (review) / 1 (error); `eval` (milestone 7).
6. **Streamlit UI** per SPEC §13: split layout, PNG page rendering cached by `(file_hash, page, dpi)`, heading bbox highlight, targets strip, Sections / JSON / Checks / Debug tabs, Go-to-page buttons, sidebar settings. *Done:* `app/streamlit_app.py`, driven headless by `tests/test_app.py`. For it the result gained `Section.bbox` and `targets_source`, and `extract()` an `on_stage` callback.
7. **Eval harness + OCR.** `run_eval.py` with SPEC §15 metrics. Add at least two labelled tenders from a different issuer before tuning any weight. Then OCR behind the interface, with a scanned tender as the third fixture. *Done:* the harness (both fixtures score 100% with the LLM off; 13 of 661 candidates are in the LLM band) and OCR behind its interface with a tesseract engine, tested with a scripted engine. *Open:* tesseract is not installed here, so the real engine is untested; the labelled tenders from other issuers and the scanned third fixture need real documents, checked by hand ([eval/labelled/README.md](../eval/labelled/README.md)).

## Commands

```bash
python -m tender_sections extract tests/fixtures/nrl_pur1011848.pdf --no-llm          # prints targets
python -m tender_sections extract tests/fixtures/nrl_pur1011848.pdf --no-llm --full --debug | jq .flat_inclusive
streamlit run app/streamlit_app.py
python -m tender_sections eval eval/labelled --report eval/report.md
```
