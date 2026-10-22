# Data model: candidates, sections, results (§2)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 2. Data model (continued): candidates and results

```python
class Candidate(BaseModel):
    line: Line
    kind: Literal["letter", "named", "numeric", "titled", "layout_only"]
    id: str | None            # "B", "2.6.1", "19", None
    id_norm: str | None       # "sec_B", "annexure_2_6_1", "clause_18"
    display_id: str           # "B", "Annexure 2.6.1", "" for an unnumbered line
    title: str                # text after the id, or the looked-up title for a bare id (§5b)
    title_source: Literal["same_line", "lines_below", "index", "none"]
    label: str                # canonical label of the title, else of the index description (§10)
    first_on_page: bool
    score: int                # 0..10
    score_breakdown: dict[str, int]
    decision: Literal["accept", "reject", "undecided"]
    decided_by: Literal["rules", "llm", "llm_whole_doc", "disabled"] | None
    level: int | None
    evidence: str | None
    confidence: float | None  # set when the LLM decides; otherwise score / 10

class Section(BaseModel):
    id: str                   # "pqc", "annexure_2_6_1", "sec_B"
    display_id: str           # "B", "Annexure 2.6.1", "" for unlettered titled sections
    title: str
    label: str                # canonical label (§10) or "other"
    level: int
    start_page: int
    end_page: int             # inclusive of children
    end_page_exclusive: int   # stops before first child
    starts_mid_page: bool
    confidence: float
    decided_by: str
    evidence: str             # the heading line
    bbox: BBox | None         # the heading line on start_page, normalized: the UI's highlight
    children: list["Section"] = []

class TargetSource(BaseModel):    # where a target's answer comes from (§10)
    section: str | None       # id of the section carrying the label (found)
    index_entry: IndexEntry | None  # the listing naming it (not_applicable, or absent although listed)

class ExtractionResult(BaseModel):
    document: DocumentInfo    # file, pages, printed_page_offset, has_bookmarks, image_only_pages, needs_ocr_pages
    targets: dict[str, list[int] | None]           # {"pqc": [11,13], "scc": null, ...} — always all five keys
    targets_status: dict[str, Literal["found", "not_applicable", "absent"]]
    targets_source: dict[str, TargetSource]          # the UI's tooltip: "listed as Not Applicable on p15"
    sections: list[Section]   # tree
    flat_inclusive: dict[str, list[int]]
    flat_exclusive: dict[str, list[int]]
    unassigned_pages: list[int]
    expected_but_missing: list[str]   # id_norm: ["annexure_17"]
    not_applicable_found: list[str]   # id_norm
    warnings: list[Warning]   # {code, message, page?}
    needs_human_review: bool
    llm_usage: LLMUsage       # candidate_calls, whole_doc_pass, input_tokens, output_tokens
    debug: DebugInfo | None   # candidates, boilerplate lines, index entries, llm transcripts (UI only)
```
