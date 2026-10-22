"""Titles → canonical labels: the vocabulary half of stage 10 (SPEC §10).

Keyword rules, not bare fuzzy matching: "SPECIAL CONDITIONS FOR MICRO AND SMALL ENTERPRISES" is
not the SCC. Phrases are matched word-aligned with a fuzzy ratio rather than as substrings, so the
f2 p69 typo "CONDTIONS" still reads as "conditions" while "UNPRICED BID" does not contain
"price bid". The rule syntax is documented on LabelSettings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Literal, NamedTuple

from rapidfuzz import fuzz

from tender_sections.config import LabelSettings
from tender_sections.models import IndexEntry, Section, TargetSource, TargetStatus

OTHER = "other"
_ACRONYM = re.compile(r"[A-Z][A-Z0-9]{1,5}")


def match_words(text: str) -> tuple[str, ...]:
    """Lower-case words: '&' reads as 'and', any other punctuation separates words."""
    return tuple(re.sub(r"[^a-z0-9]+", " ", text.lower().replace("&", " and ")).split())


def label_for_text(text: str, settings: LabelSettings) -> str:
    """The first label with a matching rule, else "other"."""
    words = match_words(text)
    for label, rules in _compile(tuple(settings.vocabulary.items())):
        for rule in rules:
            if all(
                any(alt.matches(text, words, settings.fuzzy_threshold) for alt in term)
                for term in rule
            ):
                return label
    return OTHER


def label_for(title: str, description: str | None, settings: LabelSettings) -> str:
    """The body title decides; the document's own index description is the fallback."""
    label = label_for_text(title, settings) if title else OTHER
    if label == OTHER and description:
        label = label_for_text(description, settings)
    return label


class Targets(NamedTuple):
    ranges: dict[str, list[int] | None]  # ExtractionResult.targets
    status: dict[str, TargetStatus]
    sources: dict[str, TargetSource]


def resolve_targets(
    sections: list[Section], index_entries: list[IndexEntry], settings: LabelSettings
) -> Targets:
    """Each target label → the shallowest emitted section carrying it (earliest on a tie).

    Without one, the document's own index decides between "not_applicable" (f1: SCC, SOR and
    Technical Specifications are listed under "Annexures Not Applicable") and "absent".
    Every target label is always present.
    """
    targets: dict[str, list[int] | None] = {}
    status: dict[str, TargetStatus] = {}
    sources: dict[str, TargetSource] = {}
    for target in settings.target_labels:
        carrying = [section for section in sections if section.label == target]
        if carrying:
            best = min(carrying, key=lambda section: (section.level, section.start_page))
            targets[target], status[target] = [best.start_page, best.end_page], "found"
            sources[target] = TargetSource(section=best.id)
            continue
        listed = [
            entry
            for entry in index_entries
            if entry.description and label_for_text(entry.description, settings) == target
        ]
        not_applicable = [entry for entry in listed if entry.applicability == "not_applicable"]
        targets[target] = None
        status[target] = "not_applicable" if not_applicable else "absent"
        sources[target] = TargetSource(index_entry=next(iter(not_applicable or listed), None))
    return Targets(targets, status, sources)


@dataclass(frozen=True)
class _Alternative:
    kind: Literal["acronym", "exact", "phrase"]
    words: tuple[str, ...] = ()
    pattern: re.Pattern[str] | None = None

    def matches(self, text: str, words: tuple[str, ...], threshold: float) -> bool:
        if self.pattern is not None:
            return self.pattern.search(text) is not None
        if self.kind == "exact":
            return words == self.words
        return _phrase_in(self.words, words, threshold)


def _phrase_in(phrase: tuple[str, ...], words: tuple[str, ...], threshold: float) -> bool:
    """Fuzzy ratio against every window of n-1 .. n+1 consecutive words (n = phrase length)."""
    target = " ".join(phrase)
    n = len(phrase)
    for size in range(max(1, n - 1), n + 2):
        for start in range(len(words) - size + 1):
            window = " ".join(words[start : start + size])
            if fuzz.ratio(target, window, score_cutoff=threshold):
                return True
    return False


Term = tuple[_Alternative, ...]


@cache
def _compile(
    vocabulary: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[tuple[str, list[list[Term]]]]:
    return [(label, [_rule(rule) for rule in rules]) for label, rules in vocabulary]


def _rule(rule: str) -> list[Term]:
    return [tuple(_alternative(alt.strip()) for alt in term.split("|")) for term in rule.split("+")]


def _alternative(text: str) -> _Alternative:
    if _ACRONYM.fullmatch(text):
        return _Alternative(
            "acronym", pattern=re.compile(rf"(?<![A-Za-z0-9]){re.escape(text)}(?![A-Za-z0-9])")
        )
    if text.startswith("="):
        return _Alternative("exact", words=match_words(text[1:]))
    return _Alternative("phrase", words=match_words(text))
