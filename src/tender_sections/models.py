"""Data model shared by every stage (SPEC §2).

Pages are 1-based physical everywhere. Line coordinates are normalized to 0..1 by page size.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

BBox = tuple[float, float, float, float]
Band = Literal["top", "bottom"]
TargetStatus = Literal["found", "not_applicable", "absent"]
DecidedBy = Literal["rules", "llm", "llm_whole_doc", "disabled"]

# Stable codes: the SPEC §9 table.
WarningCode = Literal[
    "ORDER_VIOLATION",
    "TARGET_LISTED_BUT_MISSING",
    "EXPECTED_MISSING",
    "NOT_APPLICABLE_FOUND",
    "SUSPICIOUS_LENGTH",
    "NO_SECTIONS",
    "UNASSIGNED_INTERIOR",
    "UNDECIDED_WITHOUT_LLM",
    "PRINTED_PAGE_INCONSISTENT",
    "PAGE_IMAGE_ONLY",
    "BOOKMARK_MISMATCH",
    "LLM_PARSE_FAILED",
    "LLM_EVIDENCE_MISMATCH",
    "LLM_UNAVAILABLE",
    "OCR_UNAVAILABLE",
]


class Warning(BaseModel):  # name fixed by SPEC §2
    code: WarningCode
    message: str
    page: int | None = None


class Line(BaseModel):
    """One logical line: y-sorted, same-baseline fragments merged (SPEC §3)."""

    page: int
    text: str  # whitespace-collapsed
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float  # max span size on the line, points
    bold_ratio: float  # bold characters / characters
    caps_ratio: float  # upper-case letters / letters; 0 below ingest.caps_min_letters
    in_table: bool = False
    is_boilerplate: bool = False
    in_index_block: bool = False
    order: int  # index within the page after the y-sort


class TableRow(BaseModel):
    bbox: BBox  # normalized
    cells: list[str]  # whitespace-collapsed; "" for an empty cell


class Table(BaseModel):
    """A ruled table found by page.find_tables()."""

    bbox: BBox  # normalized
    rows: list[TableRow] = Field(default_factory=list)


class Page(BaseModel):
    number: int  # physical, 1-based
    width: float  # points
    height: float
    printed_number: int | None = None
    # Decided in stage 2, after boilerplate: footer text alone is not a text layer. None before.
    has_text_layer: bool | None = None
    is_image_only: bool | None = None
    needs_ocr: bool | None = None
    # Character-weighted mode of the non-boilerplate lines; the document's on sparse pages.
    body_font_size: float
    lines: list[Line] = Field(default_factory=list)
    image_count: int = 0
    drawing_count: int = 0  # vector paths: a CAD drawing has many and may have no raster image
    tables: list[Table] = Field(default_factory=list)
    is_index_page: bool = False
    ocr: bool = False  # OCR added lines to this image-only page (stage 2)


class Bookmark(BaseModel):
    level: int
    title: str
    page: int  # 1-based; -1 when the bookmark has no target


class BoilerplateGroup(BaseModel):
    """Exact text repeated in one band on at least boilerplate.min_pages pages."""

    band: Band
    text: str  # as written at the first occurrence
    pages: list[int]
    first_page: int
    first_order: int


class IndexEntry(BaseModel):
    id_norm: str  # "annexure_19", "sec_B"
    display_id: str  # "Annexure 19"
    description: str | None  # None when the cell is empty or a placeholder such as "None"
    applicability: Literal["applicable", "not_applicable", "external"]
    page: int  # where the entry was read


class ParsedDocument(BaseModel):
    """The document as stages 1–3 leave it, read by every later stage."""

    file_name: str | None = None
    page_count: int
    pages: list[Page]
    bookmarks: list[Bookmark] = Field(default_factory=list)
    printed_page_offset: int | None = None
    boilerplate_groups: list[BoilerplateGroup] = Field(default_factory=list)
    index_entries: list[IndexEntry] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)


class Candidate(BaseModel):
    line: Line
    kind: Literal["letter", "named", "numeric", "titled", "layout_only"]
    id: str | None = None  # "B", "2.6.1", "19"
    id_norm: str | None = None  # "sec_B", "annexure_2_6_1"
    display_id: str = ""  # "B", "Annexure 2.6.1", "" for an unnumbered line
    title: str = ""  # text after the id, or the looked-up title of a bare id
    title_source: Literal["same_line", "lines_below", "index", "none"] = "none"
    label: str = "other"  # canonical label of the title, else of the index description
    first_on_page: bool = False
    score: int = 0  # 0..10
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    decision: Literal["accept", "reject", "undecided"] = "undecided"
    decided_by: DecidedBy | None = None
    level: int | None = None
    evidence: str | None = None
    confidence: float | None = None  # set when the LLM decides; otherwise score / 10


class Section(BaseModel):
    id: str  # "pqc", "annexure_2_6_1", "sec_B"
    display_id: str  # "B", "Annexure 2.6.1", "" for unlettered titled sections
    title: str
    label: str  # canonical label or "other"
    level: int
    start_page: int
    end_page: int  # inclusive of children
    end_page_exclusive: int  # stops before the first child
    starts_mid_page: bool
    confidence: float
    decided_by: str
    evidence: str
    bbox: BBox | None = None  # the heading line on start_page, normalized: the UI's highlight
    children: list[Section] = Field(default_factory=list)


class TargetSource(BaseModel):
    """Where a target's answer comes from (SPEC §10): the section that carries its label, else the
    tender's own index entry naming it (the UI's tooltip "listed as Not Applicable on p15")."""

    section: str | None = None  # id of the section (status found)
    index_entry: IndexEntry | None = None  # not_applicable, or absent although listed


class DocumentInfo(BaseModel):
    file: str | None
    pages: int
    printed_page_offset: int | None
    has_bookmarks: bool
    image_only_pages: list[int] = Field(default_factory=list)
    needs_ocr_pages: list[int] = Field(default_factory=list)


class LLMUsage(BaseModel):
    candidate_calls: int = 0
    whole_doc_pass: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class DebugInfo(BaseModel):
    """UI only."""

    candidates: list[Candidate] = Field(default_factory=list)
    boilerplate_lines: list[Line] = Field(default_factory=list)
    index_entries: list[IndexEntry] = Field(default_factory=list)
    llm_transcripts: list[dict[str, Any]] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    document: DocumentInfo
    targets: dict[str, list[int] | None]  # always every target label
    targets_status: dict[str, TargetStatus]
    targets_source: dict[str, TargetSource] = Field(default_factory=dict)
    sections: list[Section]  # tree
    flat_inclusive: dict[str, list[int]]
    flat_exclusive: dict[str, list[int]]
    unassigned_pages: list[int]
    expected_but_missing: list[str]
    not_applicable_found: list[str]
    warnings: list[Warning]
    needs_human_review: bool
    llm_usage: LLMUsage = Field(default_factory=LLMUsage)
    debug: DebugInfo | None = None
