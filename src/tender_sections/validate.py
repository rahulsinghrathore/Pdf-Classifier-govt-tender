"""Stage 9: document-level checks (SPEC §9).

They catch the confident-and-wrong results that score thresholds never see. A check marked as a
trigger would call the one whole-document LLM pass; with the LLM off it sets needs_human_review.
One missing listed id is only a warning (f2 Annexure 17: listed, no description, not in the body).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise

from tender_sections.assemble import Assembly
from tender_sections.config import Settings
from tender_sections.labels import label_for_text
from tender_sections.levels import keyword
from tender_sections.models import ParsedDocument, Warning, WarningCode


@dataclass
class Validation:
    warnings: list[Warning] = field(default_factory=list)
    triggers: list[WarningCode] = field(default_factory=list)  # codes that fail the document
    expected_but_missing: list[str] = field(default_factory=list)  # id_norm
    not_applicable_found: list[str] = field(default_factory=list)  # id_norm

    def add(
        self, code: WarningCode, message: str, *, page: int | None = None, trigger: bool
    ) -> None:
        self.warnings.append(Warning(code=code, message=message, page=page))
        if trigger and code not in self.triggers:
            self.triggers.append(code)


def validate(
    assembly: Assembly, doc: ParsedDocument, settings: Settings | None = None
) -> Validation:
    settings = settings or Settings()
    result = Validation()
    if not assembly.flat:
        result.add("NO_SECTIONS", "no heading was accepted", trigger=True)
        return result
    _order(assembly, settings, result)
    _against_index(assembly, doc, settings, result)
    _lengths(assembly, doc.page_count, settings, result)
    _coverage(assembly, doc, result)
    return result


def _order(assembly: Assembly, settings: Settings, result: Validation) -> None:
    letters = [
        (h.id or "", h.line.page)
        for h, s in zip(assembly.headings, assembly.flat, strict=True)
        if s.level == 1 and h.kind == "letter"
    ]
    for (a, _), (b, page) in pairwise(letters):
        if b <= a:
            result.add(
                "ORDER_VIOLATION", f"section {b} follows section {a}", page=page, trigger=True
            )
    # Each family numbers on its own: "Form 1" after "Annexure 5" is in order.
    families: dict[str, list[tuple[tuple[int, ...], str, int]]] = {}
    for h in assembly.headings:
        family = keyword(h)
        if (
            h.kind == "named"
            and family not in settings.levels.level1_keywords
            and h.id is not None
            and re.fullmatch(r"\d+(?:\.\d+)*", h.id)
        ):
            ident = tuple(int(part) for part in h.id.split("."))
            families.setdefault(family, []).append((ident, h.display_id, h.line.page))
    for numbered in families.values():
        for (a, a_name, _), (b, b_name, page) in pairwise(numbered):
            if b < a:
                result.add("ORDER_VIOLATION", f"{b_name} follows {a_name}", page=page, trigger=True)


def _against_index(
    assembly: Assembly, doc: ParsedDocument, settings: Settings, result: Validation
) -> None:
    found_ids = {h.id_norm for h in assembly.headings if h.id_norm}
    found_labels = {s.label for s in assembly.flat}
    targets = set(settings.labels.target_labels)
    for entry in doc.index_entries:
        if entry.applicability == "applicable" and entry.description:
            label = label_for_text(entry.description, settings.labels)
            if label in targets and label not in found_labels:
                result.add(
                    "TARGET_LISTED_BUT_MISSING",
                    f"{entry.display_id} ({entry.description}) is listed as applicable; "
                    f"no section carries {label}",
                    page=entry.page,
                    trigger=True,
                )

    missing = list(
        dict.fromkeys(
            e.id_norm
            for e in doc.index_entries
            if e.applicability in ("applicable", "external") and e.id_norm not in found_ids
        )
    )
    trigger = len(missing) >= settings.checks.expected_missing_trigger
    for id_norm in missing:
        result.add(
            "EXPECTED_MISSING",
            f"{id_norm} is listed in the index but has no section",
            trigger=trigger,
        )
    result.expected_but_missing = missing

    found_na = list(
        dict.fromkeys(
            e.id_norm
            for e in doc.index_entries
            if e.applicability == "not_applicable" and e.id_norm in found_ids
        )
    )
    for id_norm in found_na:
        result.add(
            "NOT_APPLICABLE_FOUND",
            f"{id_norm} is listed as not applicable but was found",
            trigger=True,
        )
    result.not_applicable_found = found_na


def _lengths(assembly: Assembly, page_count: int, settings: Settings, result: Validation) -> None:
    limit = settings.checks.suspicious_length_ratio * page_count
    for section in assembly.flat:
        span = section.end_page - section.start_page + 1
        if section.level >= 2 and span > limit:
            result.add(
                "SUSPICIOUS_LENGTH",
                f"{section.id} spans {span} of {page_count} pages",
                page=section.start_page,
                trigger=True,
            )
    top = [s for s in assembly.flat if s.level == 1]
    for a, b in pairwise(top):
        if a.start_page == a.end_page == b.start_page:  # shares its only page with the next one
            result.add(
                "SUSPICIOUS_LENGTH",
                f"{a.id} is less than a page: {b.id} starts on the same page",
                page=a.start_page,
                trigger=True,
            )


def _coverage(assembly: Assembly, doc: ParsedDocument, result: Validation) -> None:
    unassigned = set(assembly.unassigned_pages)
    prefix = 0
    while prefix + 1 in unassigned:
        prefix += 1
    suffix = doc.page_count + 1
    while suffix - 1 in unassigned and suffix - 1 > prefix:
        suffix -= 1
    interior = sorted(page for page in unassigned if prefix < page < suffix)
    if interior:
        result.add(
            "UNASSIGNED_INTERIOR", f"pages {interior} belong to no top-level section", trigger=False
        )

    starts = {s.start_page for s in assembly.flat}
    for bookmark in doc.bookmarks:
        if bookmark.level <= 2 and bookmark.page >= 1 and bookmark.page not in starts:
            result.add(
                "BOOKMARK_MISMATCH",
                f"bookmark {bookmark.title!r} has no heading on its page",
                page=bookmark.page,
                trigger=False,
            )
