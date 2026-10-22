# Stage 7: LLM adjudication (§7)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 7. Stage 7 — LLM adjudication (`llm/`)

### Client protocol (`llm/client.py`)
```python
class LLMClient(Protocol):
    def complete_json(self, *, system: str, user: str, schema: dict, max_tokens: int, effort: Effort) -> LLMReply: ...
```
`LLMReply` carries the parsed JSON, the raw text and the token counts, which feed `llm_usage` and the Debug tab's transcripts. There is one implementation, `AnthropicClient`. It reads `ANTHROPIC_API_KEY` from the environment or `.env`. The model is `llm.model`, else `LLM_MODEL`, else `claude-sonnet-5-5`; switch to `claude-haiku-5-5` for cost once accuracy is measured.

- **Schema:** enforced with structured outputs (`output_config.format`), because Claude Sonnet 5.5 rejects forced tool use.
- **Refusals:** retried server-side on Anthropic's recommended model (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`; set `llm.fallbacks: null` to turn off).
- **Failures:** a refusal of the whole chain, an API error after the SDK's retries, or an answer cut off at `max_tokens` raises `LLMError`. The batch is then rejected (`decided_by = "disabled"`) with warning `LLM_UNAVAILABLE`. A missing `ANTHROPIC_API_KEY` is a setup error instead: `LLMNotConfigured` when the client is built, so the CLI exits 1 and the UI shows it.
- **Invalid answers:** each answer is validated with pydantic. On failure it is retried once with the validation error appended; then the batch is rejected with `LLM_PARSE_FAILED`.

Effort is `low` for these yes/no verdicts (the starting point for classification on Sonnet 5.5) and `medium` for the whole-document pass (§9). Tests use `FakeLLMClient`; **no test may hit the network**. `tests/conftest.py` turns the LLM off unless a test hands in a fake, and makes building the real client fail.

### Per-candidate digest (`llm/adjudicate.py`)
Batch all undecided candidates of one document into one call (`llm.max_candidates_per_call`, 40). Per candidate:

```
Candidate 1
<<PAGE 59>>  (physical; printed 59)
Previous accepted heading: "Annexure 19 — SCHEDULE OF RATES" (level 2, page 58)
Next accepted heading: "Annexure 20 — SPECIAL CONDTIONS OF CONTRACT" (level 2, page 69)
Document's own index: Annexure 19 = "Schedule Of Rates (SOR)" (applicable, page 17)
Candidate line: "SCHEDULE OF RATES"   [first on page, 24 pt vs body 10, bold, capitals, no numbering; reads as sor, repeats the previous heading's title, score 4/10]
Page 59 text after the candidate (first 400 characters):
"1.Tender No. 2.Job Name. 3.Quoted Currency. Please do not write the price here. This SOR is for information…"
```

Ask for, per candidate, the verdict only:
```json
{"candidate": 1, "decision": "reject" | "accept", "evidence": "exact passage from that page",
 "confidence": 0.0–1.0, "reason": "one sentence"}
```
Candidates are numbered because one page can hold several. The level is **not** asked for: levels come from §6. That keeps the trap safety net (§14) independent of the model.

System prompt essentials (`llm/prompts.py`): *You decide whether a line is the heading that starts a NEW section of a tender document. A line in a table of contents, an annexure list, a checklist cell, or a cross-reference inside a sentence is NOT a section start. A label on the tender's cover page (`PART–I: UNPRICED BID`, `(Domestic Open Tender)`) is NOT a section start. A title repeated on the cover page or second page of a section that already started is NOT a new section. An unnumbered title that continues the previous annexure is NOT a new section unless the document's index lists it.*

**Evidence verification (mandatory)**: `evidence` must be a case-insensitive substring of the page's non-boilerplate text. If not → the decision is discarded, candidate → `reject`, warning `LLM_EVIDENCE_MISMATCH`. This stops the model from "finding" Annexure 17 (f2) or Annexure 4 (f1) because they appear in the index.

`confidence` for LLM-decided sections = `min(llm_confidence, 0.85)`; for rules-decided = `score / 10`.

**On the fixtures** (one real run, Claude Sonnet 5.5, `low`): all 13 undecided candidates were rejected — f1 p17; f2 p1 (both cover labels, PART–I at 0.95), p29, p31, p32 (lettered sub-headings of Annexure 3), p70 and p80 (letterhead). Both fixtures reproduce their ground truth with the LLM on. One call per tender, about 5.8k input and 1k output tokens in all.
