"""Every tunable of the pipeline. Stage modules take numbers from here, never literals.

Precedence: code defaults < config.yaml < TENDER_* environment variables < keyword arguments.
Nested keys use a double underscore in the environment: TENDER_BOILERPLATE__MIN_PAGES=4.
"""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_CONFIG_FILE: ContextVar[Path | None] = ContextVar("tender_sections_config_file", default=None)


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestSettings(_Section):
    """Stage 1 (SPEC §3)."""

    merge_baseline_ratio: float = 0.3  # one line if vertical centres differ < ratio × font size
    max_line_slope: float = 0.05  # |direction.y| above this is rotated text (stamps, watermarks)
    caps_min_letters: int = 4  # caps_ratio is 0 below this many letters
    font_size_bucket: float = 0.5  # sizes are rounded to this before taking the body-size mode
    default_body_font_size: float = 10.0  # body size of a document without text
    body_font_min_chars: int = 200  # sparser pages take the document's body size
    detect_tables: bool = True  # page.find_tables() → Line.in_table
    min_table_rows: int = 2  # a one-row box spanning the page is a frame (f2 pp70–78)
    printed_number_top_band: float = 0.10
    printed_number_bottom_band: float = 0.90
    printed_page_of_n: str = r"Page\s+(\d+)\s+of\s+(\d+)"  # kept only when N == page count
    printed_page_bare: str = r"-?\s*(\d{1,4})\s*-?"  # a band line that is only a number
    printed_offset_min_agreement: float = 0.8  # share of numbered pages that must agree


class BoilerplateSettings(_Section):
    """Stage 2 running headers and footers (SPEC §4)."""

    top_band: float = 0.12  # line.y0 below this is in the top band
    bottom_band: float = 0.90  # line.y1 above this is in the bottom band
    min_pages: int = 3  # exact text in one band on this many distinct pages is boilerplate
    # Boilerplate whenever in a band, matched case-insensitively anywhere in the line.
    page_number_patterns: tuple[str, ...] = (
        r"\bPage\s+\d+\s+of\s+\d+\b",
        r"^\d{1,4}$",
        r"^-\s*\d+\s*-$",
        r"Sys\.\s*Gen\.",
    )


class TextLayerSettings(_Section):
    """Stage 2 text-layer decision, made after boilerplate (SPEC §4)."""

    min_chars: int = 20  # non-boilerplate, non-space characters needed for a text layer
    min_vector_paths: int = 50  # this many vector paths is a drawing even without a raster image


class OCRSettings(_Section):
    """OCR of image-only pages (SPEC §3). Off: such a page falls inside the section around it."""

    enabled: bool = False
    engine: Literal["tesseract", "paddle"] = "tesseract"  # paddle is not implemented yet
    dpi: int = 300  # render resolution of a page sent to OCR
    languages: str = "eng"  # tesseract language codes; "eng+hin" for bilingual tenders
    min_word_confidence: float = 60.0  # tesseract's 0–100; less confident words are dropped


class PatternSettings(_Section):
    """Structural heading regexes (SPEC §5b), shared by boilerplate, index blocks and candidates.

    Lettered ids and roman numerals are upper-case only, so "a) …" list items and words such as
    "Civil" are not headings; the keywords themselves match in any case.
    """

    letter: str = r"^([A-Z])[.)]\s+(.{3,120})$"
    named: str = (
        r"^(?i:(annexure|appendix|schedule|section|part|chapter|form|format|exhibit))"
        r"\s*[-–:]?\s*([IVXLC]+|\d+(?:\.\d+)*[A-Za-z]?)\b[\s:–-]*(.*)$"
    )
    numeric: str = r"^(\d+(?:\.\d+)*)[.)]?\s*(\(?[A-Z]\)?)?\s+(.{3,120})$"
    list_item: str = r"^\(?(?:[a-z]|[ivx]{1,4})[.)]\s"  # "a) …", "(iv) …": never a heading


class IndexSettings(_Section):
    """Stage 3 contents / annexure-list blocks (SPEC §5a)."""

    min_entries: int = 5  # listed ids on one page that make it an index page
    min_entries_with_title: int = 4  # … when the page has a contents-like title
    # Rows are titles, not clauses. A sanity guard; the f2 ATC clause table is excluded because
    # bare letters count as ids only under a contents-like title.
    max_description_chars: int = 100  # median description length of an index table
    line_max_chars: int = 60  # line route: a listed id line is this short
    line_edge_tolerance: float = 0.03  # line route: listed ids share a left edge
    title_pattern: str = (
        r"(?i)(?:table of contents|contents|index|list of annexures?|annexures? lists?)\s*:?"
    )
    not_applicable_pattern: str = r"(?i)\bnot\s+applicable\b"
    external_pattern: str = (
        r"(?i)\b(?:website|link|available at|refer .* portal|separately|to be downloaded)\b"
    )
    empty_description_pattern: str = r"(?i)none|nil|n/?a|-+|—"  # a cell that says nothing
    serial_cell_pattern: str = r"\d{1,3}[.)]?"  # a "Sl. No." cell before the id cell is skipped


class CandidateSettings(_Section):
    """Stage 4 heading candidates (SPEC §5b)."""

    titled_max_chars: int = 90
    titled_max_words: int = 10
    layout_only_max_chars: int = 90
    layout_only_font_delta: float = 1.5  # font_size >= body + delta
    layout_only_bold_ratio: float = 0.6
    title_below_max_y: float = 0.5  # a bare id's title is looked up in the top half of the page
    title_below_font_delta: float = 1.5
    title_below_bold_ratio: float = 0.5
    title_below_size_tolerance: float = 0.5  # lines this close in size form one title group


class ScoringSettings(_Section):
    """Stage 5 scores, 0–10 (SPEC §5c)."""

    first_on_page: int = 3
    top_of_page: int = 1  # not first, but y0 < top_of_page_y
    top_of_page_y: float = 0.25
    emphasis: int = 3
    emphasis_bold_ratio: float = 0.5
    emphasis_font_delta: float = 1.5
    emphasis_caps_ratio: float = 0.7
    pattern_letter_caps: int = 3
    pattern_letter_title_case: int = 2
    pattern_letter_other: int = 1
    pattern_named: int = 3
    pattern_titled: int = 3
    pattern_numeric: int = 1
    pattern_layout_only: int = 0
    title_caps_ratio: float = 0.7  # a letter heading's title in capitals
    title_case_ratio: float = 0.6  # share of words of 4+ letters that start upper-case
    listed: int = 1
    in_table_or_index: int = -5
    sentence_like: int = -5
    sentence_max_chars: int = 90
    sentence_max_words: int = 12
    sentence_caps_ratio: float = 0.5
    sentence_endings: tuple[str, ...] = (",", ";", "&")
    sentence_end_words: tuple[str, ...] = ("and", "or")
    letter_reuse: int = -4
    unlisted_letter: int = -5  # the contents lists lettered sections, but not this one
    repeat_title: int = -5
    repeat_window_pages: int = 2
    max_score: int = 10
    accept_at: int = 8  # score >= accept_at → accept
    reject_at: int = 3  # score <= reject_at → reject; in between → LLM


_VOCABULARY: dict[str, tuple[str, ...]] = {
    "nit": ("notice inviting tender", "NIT"),
    "pqc": (
        "pre-qualification criteria",
        "prequalification criteria",
        "PQC",
        "eligibility criteria",
        "qualifying requirements",
        "bidder qualification criteria",
        "BQC",
    ),
    "brc": ("bid rejection criteria", "BRC"),
    "atc": ("agreed terms and conditions", "ATC"),
    "scc": ("special conditions + contract|SCC", "special purchase conditions", "SPC"),
    "sor": (
        "schedule of rates",
        "SOR",
        "price schedule",
        "price bid",
        "bill of quantities",
        "BOQ",
    ),
    "tech_spec": (
        "technical + specification",
        "tech spec",
        "technical requirements",
        "particular specifications",
    ),
    "gcc": ("general conditions of contract", "GCC", "general purchase conditions", "GPC"),
    "itb": ("instructions to bidders", "ITB", "instructions to tenderers"),
    "checklist": ("checklist", "check list"),
    "annexure_list": ("list of annexures", "annexure lists", "tender annexures", "=annexures"),
    "scope": ("scope of work", "scope of supply", "SOW"),
    "bank_guarantee": ("bank guarantee", "surety bond", "performance security", "EMD"),
    "declarations": (
        "declaration",
        "undertaking",
        "affidavit",
        "integrity pact",
        "code of integrity",
    ),
}


class LabelSettings(_Section):
    """Title → canonical label (SPEC §10). The first label with a matching rule wins.

    A rule is terms joined by "+", all required; "|" separates alternatives within a term. A term
    in capitals is an acronym (whole upper-case word); "=" marks a phrase that must be the whole
    title; any other term is a phrase, matched word-aligned with a fuzzy ratio. "&" reads as "and"
    and punctuation as a space, so "agreed terms & conditions" and "pre-qualification" need no
    separate entries.
    """

    fuzzy_threshold: float = 90
    vocabulary: dict[str, tuple[str, ...]] = Field(default_factory=lambda: dict(_VOCABULARY))
    target_labels: tuple[str, ...] = ("pqc", "atc", "scc", "sor", "tech_spec")  # one line per label


class LevelSettings(_Section):
    """Stage 6 levels and emission (SPEC §6)."""

    # Unlettered top-level sections are recognised through these labels (f2 NIT, PQC, BRC, ATC …).
    level1_labels: tuple[str, ...] = (
        "nit",
        "pqc",
        "brc",
        "atc",
        "annexure_list",
        "itb",
        "gcc",
        "scc",
        "sor",
        "tech_spec",
        "scope",
        "checklist",
    )
    level1_keywords: tuple[str, ...] = ("section", "part", "chapter")  # other named ids: level 2+
    max_emit_level: int = 4  # deeper headings stay in debug
    # Numbered clauses (GPC 1–41, SCC 1–30) stay internal; while they do, the LLM never sees them.
    emit_numeric_clauses: bool = False
    layout_font_step: float = 2.0  # a layout-only heading this much smaller sits one level deeper


Effort = Literal["low", "medium", "high", "xhigh", "max"]


class LLMSettings(_Section):
    """Stage 7 adjudication and the one-shot whole-document fallback (SPEC §7, §9)."""

    enabled: bool = True
    model: str | None = None  # None: LLM_MODEL from the environment or .env, else default_model
    default_model: str = "claude-sonnet-5-5"
    effort: Effort = "low"  # a yes/no per line: low is Sonnet 5.5's starting point for classifying
    whole_doc_effort: Effort = "medium"  # rebuilding the whole section list is the harder task
    max_tokens: int = 16000
    max_candidates_per_call: int = 40
    digest_chars: int = 400  # page text after the candidate, in its digest
    whole_doc_page_chars: int = 300  # first non-boilerplate characters of each page
    confidence_cap: float = 0.85  # an LLM-decided section's confidence never exceeds this
    fallbacks: str | None = "default"  # server-side refusal fallback on the Claude API; None: off
    timeout_seconds: float = 120.0


class ValidateSettings(_Section):
    """Stage 9 document-level checks (SPEC §9)."""

    suspicious_length_ratio: float = 0.4  # a level-2+ section longer than this share of the pages
    expected_missing_trigger: int = 2  # this many listed ids without a section fails the document


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TENDER_", env_nested_delimiter="__", extra="forbid"
    )

    ingest: IngestSettings = Field(default_factory=IngestSettings)
    boilerplate: BoilerplateSettings = Field(default_factory=BoilerplateSettings)
    text_layer: TextLayerSettings = Field(default_factory=TextLayerSettings)
    ocr: OCRSettings = Field(default_factory=OCRSettings)
    patterns: PatternSettings = Field(default_factory=PatternSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    candidates: CandidateSettings = Field(default_factory=CandidateSettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    labels: LabelSettings = Field(default_factory=LabelSettings)
    levels: LevelSettings = Field(default_factory=LevelSettings)
    checks: ValidateSettings = Field(default_factory=ValidateSettings)  # stage 9
    llm: LLMSettings = Field(default_factory=LLMSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        path = _CONFIG_FILE.get()
        if path is None:
            return init_settings, env_settings
        yaml_source = YamlConfigSettingsSource(
            settings_cls, yaml_file=path, yaml_file_encoding="utf-8"
        )
        return init_settings, env_settings, yaml_source


def load_settings(path: str | Path | None = None) -> Settings:
    """Settings from a YAML file (if given) with environment overrides applied on top."""
    if path is None:
        return Settings()
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    token = _CONFIG_FILE.set(path)
    try:
        return Settings()
    finally:
        _CONFIG_FILE.reset(token)
