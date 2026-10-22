# Tender Section Extractor — Technical Specification

The detailed design, one file per pair of stages under `docs/spec/`. `CLAUDE.md` has the rules and the short version; these files have the algorithms, data model, prompts, UI spec and test plan. When the two disagree, the spec wins for *how*, `CLAUDE.md` wins for *what you may not do*. Code and docs cite sections by number (`SPEC §5c`); the table says where each one lives.

| § | Topic | File |
|---|---|---|
| 0–1 | Problem statement, pipeline overview | [spec/overview.md](spec/overview.md) |
| 2 | Data model: `Line`, `Table`, `Page`, `IndexEntry`, `ParsedDocument` | [spec/data-model.md](spec/data-model.md) |
| 2 | Data model: `Candidate`, `Section`, `ExtractionResult` | [spec/results-model.md](spec/results-model.md) |
| 3–4 | Stage 1 ingest, stage 2 boilerplate and the text layer | [spec/ingest.md](spec/ingest.md) |
| 5a–5b | Stage 3 index blocks, stage 4 candidates and bare-id titles | [spec/index-candidates.md](spec/index-candidates.md) |
| 5c | Stage 5 scoring, the worked examples, the LLM band | [spec/scoring.md](spec/scoring.md) |
| 6, 8 | Stage 6 levels, stage 8 assembly and end pages | [spec/levels-assemble.md](spec/levels-assemble.md) |
| 7 | Stage 7 LLM adjudication and evidence | [spec/llm.md](spec/llm.md) |
| 9–10 | Stage 9 validation codes, stage 10 vocabulary and targets | [spec/validate-labels.md](spec/validate-labels.md) |
| 11–13 | Config, CLI, Streamlit UI | [spec/config-cli-ui.md](spec/config-cli-ui.md) |
| 14–16 | Tests, evaluation harness, known limitations | [spec/tests-eval.md](spec/tests-eval.md) |

Two hand-verified fixtures drive everything; every algorithm in the spec cites them:

| | `nrl_pur1011567` | `nrl_pur1011848` |
|---|---|---|
| type | GeM **supply** tender, 67 pp | **works** tender, 85 pp |
| level-1 headings | lettered: `A.` `B.` `C.` `D.` | **unlettered**: `NOTICE INVITING TENDER`, `PRE-QUALIFICATION CRITERIA (PQC)`, … |
| SCC / SOR / Tech Specs | listed as **Not Applicable** (Annexures 19/20/21 on p15) | **present** as Annexures 20 / 19 / 21 |
| quirks | header changes at p14; `Annexure 18` out of block order on p52 | running section titles on pp71–78 and 80–83; SOR has its own `SOR Page X of 10` footer; pp84–85 are image-only drawings; Annexure 17 listed but absent; typo `CONDTIONS` on p69 |
