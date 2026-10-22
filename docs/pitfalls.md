# Things that look like good ideas and are not

Part of the project docs; start at [CLAUDE.md](../CLAUDE.md).

- Sending the whole PDF to the model and asking for the JSON. Fine as a *baseline* in `eval/`, not as the pipeline: it miscounts pages without markers, invents annexures from the index (`Annexure 17` in fixture 2 is listed and does not exist), and does not scale to 400-page EPC tenders.
- Using a vector store "for the metadata". The section map *is* the metadata; nothing is being retrieved.
- Looking only for the five target headings. The tree is what makes the targets resolvable: SOR is `Annexure 19` in one tender and `Section-IV` in another, and the index is what tells you SCC is Not Applicable rather than missing.
- Treating `score ≥ 8` as truth without the document-level checks. The checks catch the confident-and-wrong cases that thresholds never see.
- Dropping the `evidence` requirement because the model "usually" gets it right.
- Fuzzy-matching labels without keyword rules. `SPECIAL CONDITIONS FOR MICRO AND SMALL ENTERPRISES` is not the SCC.
- Tuning a weight until a hand-made list of undecided pages comes out. SPEC §5c's first list missed whole kinds of lines (bold numbered clauses, lettered sub-headings); find the rule that explains the band instead.
- Trusting a check that found nothing. A trap test whose text matches no line on its page passes without testing anything; `tests/helpers.anchor` makes it fail instead.
