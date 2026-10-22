# Design decisions

Part of the project docs; start at [README.md](../README.md). The rules these decisions became: [CLAUDE.md](../CLAUDE.md). The tempting alternatives that failed: [pitfalls.md](pitfalls.md). "f1" and "f2" are the two test tenders (supply, 67 pages; works, 85 pages).

## Framing

1. **Segment the document, do not search it.** Find where each section starts, compute where it ends, label the titles. No RAG, embeddings or vector store: nothing is being retrieved, and the section map *is* the metadata.
2. **Extract the whole tree, then resolve the targets.** The five targets sit at different depths (`B. PRE-QUALIFICATION CRITERIA` at the top of f1, SOR / SCC / technical specifications as Annexures 19–21 in f2), so each target resolves to the *shallowest* section carrying its label: Annexure 21, not the `2. Technical Specification:` clause inside it.
3. **Say why a target is missing.** `not_applicable` (the tender's own list says so; f1 p15) and `absent` are different answers to the business, so the tender's index is read, not skipped.

## Pipeline rules (each one fixed a wrong answer on a fixture)

4. **Reading order before anything else.** Lines are sorted by y and same-baseline fragments merged first: PyMuPDF's block order puts `Definition:` above `Annexure 18` (f1 p52) and splits `D.` from `Benefits Under…` (f1 p25).
5. **Running headers are exact text repeated on 3 or more pages**, spacing ignored. Not a percentage: f1's header changes at p14. Not digit-normalized: that would merge `Annexure 2` and `Annexure 3`. Vocabulary titles used as headers are stripped too (f2 pp71–78), and the first one returns if no section carries its label.
6. **"Image-only" is decided after stripping.** f2 pp84–85 hold 42 characters of footer around a drawing. They have no text layer, and they need no OCR: the end-page rule already puts them inside Technical Specifications.
7. **Scores, not first matches.** Each candidate gets 0–10 from weighted evidence (first on the page, emphasis, the pattern, listed in the index) minus penalties: inside a table or index −5, reads like a sentence −5, repeats the last heading's title −5. 8 or more is accepted, 3 or less rejected.
8. **Unlettered headings come from the vocabulary.** `NOTICE INVITING TENDER` (f2, 10 pt bold) is a top-level section because it maps to `nit`, not because of its font; a bold line that maps to nothing (f1 p17) goes to the LLM.
9. **End pages come from the subtree, in code.** A section ends where the next heading outside its own subtree starts. An orphan `Annexure 7.2` (there is no 7) hangs under the top-level section, so it ends Annexure 6. Both inclusive and exclusive ranges are emitted.
10. **Labels by keyword rules first, fuzzy matching second.** `SPECIAL CONDITIONS FOR MICRO AND SMALL ENTERPRISES` (f2 p29) is not the SCC. Word-aligned fuzzy matching still reads the typo `CONDTIONS` (f2 p69) and does not find `price bid` inside `UNPRICED BID`.
11. **Numbered clauses stay internal.** GPC 1–41 and SCC 1–30 are not emitted and never sent to the LLM (`levels.emit_numeric_clauses: false`), which keeps the tree readable and the LLM band small.
12. **Pages are physical everywhere.** Printed numbers count only from the series whose `of N` is the page count (f2's SOR numbers its own pages 1–10). A sparse page takes the document's body font size (a cover holding one 36 pt title); a one-row "table" is a page frame (f2 pp70–78).
13. **Every number lives in `config.py`**, and `config.yaml` is kept equal to it by a test, so tuning never means editing a stage.

## The LLM

14. **A judge, not a parser.** Called only for the 4–7 band and for at most one whole-document pass; it sees page digests with `<<PAGE n>>` markers, never the PDF, and never computes a page range. Sending the whole PDF miscounts pages and invents f2's Annexure 17 from the index.
15. **Every answer quotes its page.** An answer whose evidence is not on the claimed page is discarded. Answers are verdicts only: levels stay with the rules, so a wrong "yes" lands deep in the tree. The one exception is the cover label `PART–I: UNPRICED BID` (f2 p1), a top-level Part heading by rule; only the prompt protects it, and the real run rejected it at 0.95.
16. **Claude API settings.** `claude-sonnet-5-5` by default. The answer schema goes in structured outputs, because Sonnet 5.5 rejects forced tool use. Effort is `low` for yes/no verdicts and `medium` for the rebuild. The server-side refusal fallback is on (`llm.fallbacks: null` turns it off), and an LLM's confidence is capped at 0.85.
17. **Degrade on outages, stop on setup errors.** An API error, refusal or cut-off reply rejects the band with `LLM_UNAVAILABLE`, and extraction goes on. A missing API key raises `LLMNotConfigured`, because someone has to fix it.

## Interfaces and process

18. **One function, three front ends.** The command line, the app and the harness all call `extract()`. The app holds no pipeline logic and imports only public names, so the result carries what the app draws: each heading's box (`Section.bbox`) and each target's source (`targets_source`).
19. **Exit codes 0 / 2 / 1.** 2 means "needs human review", so scripts can route documents; every error, bad arguments included, is 1.
20. **OCR is off by default and sits behind an interface.** Only a section that *starts* on an image-only page needs it; tesseract is the engine, and tests use a scripted one.
21. **The fixtures are the contract.** Both must reach their hand-verified ground truth with the LLM off. `.expected.json` is never edited to pass a test, no test touches the network, and weights are tuned only after labelled tenders from other issuers have been measured with the harness.
