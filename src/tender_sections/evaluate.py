"""Evaluation harness (SPEC §15): extract() over labelled tenders, scored against ground truth.

A labelled tender is <name>.pdf next to <name>.expected.json, in the fixtures' format. Read:
targets, targets_status, flat_inclusive (id → [start, end]) and tree_levels (id → level); a
level-1 id may be named in level1_titles instead (f1 keys its letters "A"–"D" in tree_levels).
Error buckets are a first guess from the debug data, to point at a cause, not part of any score.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tender_sections import extract
from tender_sections.config import LabelSettings, Settings
from tender_sections.labels import OTHER, label_for_text
from tender_sections.llm import LLMClient
from tender_sections.models import Candidate, ExtractionResult, Line, Section

BUCKETS = (
    "index_page",
    "cross_reference",
    "repeat_title",
    "mid_page",
    "ocr",
    "boilerplate",
    "level",
    "label",
    "other",
)
F1_LEVELS = (1, 2)  # section F1 is reported at these levels
_REFERENCE = re.compile(r"(?i)\b(?:refer|as per|vide|mentioned in|specified in|enclosed)\b")


@dataclass(frozen=True)
class Truth:
    """A labelled tender's expected JSON, as far as the harness reads it."""

    targets: dict[str, list[int] | None]
    status: dict[str, str]
    sections: dict[str, tuple[int, int]]  # id → inclusive (start, end)
    levels: dict[str, int]  # id → level, for the ids the file gives a level

    @classmethod
    def load(cls, path: Path) -> Truth:
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = [
            key for key in ("targets", "targets_status", "flat_inclusive") if key not in data
        ]
        if missing:
            raise ValueError(f"{path.name} has no {', '.join(missing)}")
        return cls.parse(data)

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Truth:
        sections = {key: (span[0], span[1]) for key, span in _plain(data["flat_inclusive"]).items()}
        tree, top = _plain(data.get("tree_levels", {})), set(data.get("level1_titles", {}))
        levels = {key: tree.get(key, 1) for key in sections if key in tree or key in top}
        return cls(_plain(data["targets"]), dict(data["targets_status"]), sections, levels)

    def parents(self) -> dict[str, str | None]:
        """Each levelled section's parent: the deepest one of a lower level whose range holds it,
        the latest on a tie. An orphan Annexure 7.2 gets the level-1 section, as in assemble."""
        parents: dict[str, str | None] = {}
        for key, level in self.levels.items():
            start, end = self.sections[key]
            holders = [
                (self.levels[other], self.sections[other][0], other)
                for other in self.levels
                if self.levels[other] < level
                and self.sections[other][0] <= start
                and end <= self.sections[other][1]
            ]
            parents[key] = max(holders)[2] if holders else None
        return parents


@dataclass(frozen=True)
class Error:
    bucket: str  # one of BUCKETS
    page: int | None
    what: str


@dataclass
class DocumentScore:
    name: str
    targets: dict[str, tuple[bool, bool]]  # label → (range right, status right)
    starts: dict[int, tuple[int, int]]  # level → (start page right, expected sections)
    found: dict[int, tuple[int, int, int]]  # level → (right, emitted, expected): section F1
    nesting: tuple[int, int]  # (parent right, sections found at their start page)
    false_headings: tuple[int, int]  # (emitted but not in the truth, emitted)
    llm_calls: int
    band: tuple[int, int]  # (candidates the LLM judged or would have, candidates)
    tokens: tuple[int, int]  # (input, output)
    needs_human_review: bool
    errors: list[Error] = field(default_factory=list)


@dataclass
class Evaluation:
    directory: Path
    llm: bool
    documents: list[DocumentScore]
    skipped: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        docs = self.documents
        labels = list(dict.fromkeys(label for d in docs for label in d.targets))
        levels = sorted({level for d in docs for level in d.starts})
        buckets = Counter(error.bucket for d in docs for error in d.errors)
        return {
            "documents": len(docs),
            "llm": self.llm,
            "targets": {
                "range": _share(*_sum((ok, 1) for d in docs for ok, _ in d.targets.values())),
                "status": _share(*_sum((ok, 1) for d in docs for _, ok in d.targets.values())),
                "by_label": {
                    label: {
                        "range": _share(
                            *_sum((d.targets[label][0], 1) for d in _with(docs, label))
                        ),
                        "status": _share(
                            *_sum((d.targets[label][1], 1) for d in _with(docs, label))
                        ),
                    }
                    for label in labels
                },
            },
            "start_page_match": {
                level: _share(*_sum(d.starts.get(level, (0, 0)) for d in docs)) for level in levels
            },
            "section_f1": {level: _f1(docs, level) for level in F1_LEVELS},
            "nesting_accuracy": _share(*_sum(d.nesting for d in docs)),
            "false_heading_rate": _share(*_sum(d.false_headings for d in docs)),
            "documents_calling_llm": _share(sum(d.llm_calls > 0 for d in docs), len(docs)),
            "candidates_in_llm_band": _share(*_sum(d.band for d in docs)),
            "tokens": {
                "input": sum(d.tokens[0] for d in docs),
                "output": sum(d.tokens[1] for d in docs),
            },
            "needs_human_review": sum(d.needs_human_review for d in docs),
            "error_buckets": {bucket: buckets[bucket] for bucket in BUCKETS if buckets[bucket]},
        }


def run_eval(
    directory: str | Path,
    settings: Settings | None = None,
    *,
    llm: LLMClient | None = None,
    on_document: Callable[[str], None] | None = None,
) -> Evaluation:
    """extract() on every labelled tender in the directory, scored. Unpaired files are skipped."""
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(f"not a directory: {directory}")
    settings = settings or Settings()
    documents, skipped = [], []
    for pdf in sorted(directory.glob("*.pdf")):
        truth_path = pdf.with_name(f"{pdf.stem}.expected.json")
        if not truth_path.is_file():
            skipped.append(f"{pdf.name}: no {truth_path.name}")
            continue
        truth = Truth.load(truth_path)
        if on_document is not None:
            on_document(pdf.stem)
        result = extract(pdf, settings, llm=llm, debug=True)
        documents.append(score_document(pdf.stem, result, truth, settings))
    for truth_path in sorted(directory.glob("*.expected.json")):
        stem = truth_path.name.removesuffix(".expected.json")
        if not (directory / f"{stem}.pdf").is_file():
            skipped.append(f"{truth_path.name}: no {stem}.pdf")
    return Evaluation(directory, llm is not None or settings.llm.enabled, documents, skipped)


def score_document(
    name: str, result: ExtractionResult, truth: Truth, settings: Settings | None = None
) -> DocumentScore:
    settings = settings or Settings()
    flat = list(_walk(result.sections))
    emitted = {(s.id, s.start_page) for s in flat}
    expected = {(key, span[0]) for key, span in truth.sections.items()}
    starts: dict[int, tuple[int, int]] = {}
    for key, level in sorted(truth.levels.items(), key=lambda item: item[1]):
        right, total = starts.get(level, (0, 0))
        starts[level] = (right + ((key, truth.sections[key][0]) in emitted), total + 1)
    found = {}
    for level in F1_LEVELS:
        mine = {(s.id, s.start_page) for s in flat if s.level == level}
        theirs = {(key, truth.sections[key][0]) for key, lv in truth.levels.items() if lv == level}
        found[level] = (len(mine & theirs), len(mine), len(theirs))
    parents, truth_parents = _parents(result.sections), truth.parents()
    placed = [key for key in truth.levels if (key, truth.sections[key][0]) in emitted]
    candidates = result.debug.candidates if result.debug else []
    usage = result.llm_usage
    return DocumentScore(
        name=name,
        targets={
            label: (
                result.targets.get(label) == span,
                result.targets_status.get(label) == truth.status.get(label),
            )
            for label, span in truth.targets.items()
        },
        starts=starts,
        found=found,
        nesting=(sum(parents[key] == truth_parents[key] for key in placed), len(placed)),
        false_headings=(sum((s.id, s.start_page) not in expected for s in flat), len(flat)),
        llm_calls=usage.candidate_calls + int(usage.whole_doc_pass),
        band=(sum(c.decided_by in ("llm", "disabled") for c in candidates), len(candidates)),
        tokens=(usage.input_tokens, usage.output_tokens),
        needs_human_review=result.needs_human_review,
        errors=_errors(result, truth, settings),
    )


def render_report(evaluation: Evaluation) -> str:
    """The Markdown report: summary, targets by label, per document, error buckets, errors."""
    docs = evaluation.documents
    targets = [ok for d in docs for ok in d.targets.values()]
    lines = [
        "# Evaluation report",
        "",
        f"{len(docs)} labelled tenders from `{evaluation.directory}`, LLM "
        f"{'on' if evaluation.llm else 'off'}. Written by `python -m tender_sections eval`; "
        "the metrics are SPEC §15's.",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "|---|---|",
        f"| target ranges exactly right | {_fraction(sum(r for r, _ in targets), len(targets))} |",
        f"| target status right | {_fraction(sum(s for _, s in targets), len(targets))} |",
    ]
    for level in sorted({level for d in docs for level in d.starts}):
        right, total = _sum(d.starts.get(level, (0, 0)) for d in docs)
        lines.append(f"| start page right, level {level} | {_fraction(right, total)} |")
    for level in F1_LEVELS:
        f1 = _f1(docs, level)
        lines.append(f"| section F1, level {level} | {'–' if f1 is None else f'{f1:.3f}'} |")
    lines += [
        f"| nesting (parent right) | {_fraction(*_sum(d.nesting for d in docs))} |",
        f"| false headings | {_fraction(*_sum(d.false_headings for d in docs))} |",
        f"| documents calling the LLM | {_fraction(sum(d.llm_calls > 0 for d in docs), len(docs))} |",
        f"| candidates in the LLM band | {_fraction(*_sum(d.band for d in docs))} |",
        f"| tokens in / out | {sum(d.tokens[0] for d in docs)} / {sum(d.tokens[1] for d in docs)} |",
        f"| needs human review | {_fraction(sum(d.needs_human_review for d in docs), len(docs))} |",
        "",
        "## Targets by label",
        "",
        "| label | range | status |",
        "|---|---|---|",
    ]
    for label in dict.fromkeys(label for d in docs for label in d.targets):
        hits = [d.targets[label] for d in _with(docs, label)]
        lines.append(
            f"| {label} | {_fraction(sum(r for r, _ in hits), len(hits))} "
            f"| {_fraction(sum(s for _, s in hits), len(hits))} |"
        )
    lines += [
        "",
        "## Per document",
        "",
        "| tender | target ranges | level-1 F1 | level-2 F1 | nesting | false headings | LLM calls | review |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for d in docs:
        f1 = [_f1([d], level) for level in F1_LEVELS]
        lines.append(
            f"| {d.name} | {sum(r for r, _ in d.targets.values())}/{len(d.targets)} "
            f"| {' | '.join('–' if v is None else f'{v:.3f}' for v in f1)} "
            f"| {d.nesting[0]}/{d.nesting[1]} | {d.false_headings[0]}/{d.false_headings[1]} "
            f"| {d.llm_calls} | {'yes' if d.needs_human_review else 'no'} |"
        )
    errors = [(d.name, error) for d in docs for error in d.errors]
    buckets = Counter(error.bucket for _, error in errors)
    lines += ["", "## Error buckets", ""]
    if not errors:
        lines.append("No errors.")
    else:
        lines += ["| bucket | errors |", "|---|---|"]
        lines += [f"| {bucket} | {buckets[bucket]} |" for bucket in BUCKETS if buckets[bucket]]
        lines += ["", "## Errors", "", "| tender | page | bucket | what |", "|---|---|---|---|"]
        lines += [
            f"| {name} | {'' if e.page is None else e.page} | {e.bucket} | {e.what.replace('|', '/')} |"
            for name, e in errors
        ]
    if evaluation.skipped:
        lines += ["", "## Skipped", "", *(f"- {note}" for note in evaluation.skipped)]
    return "\n".join(lines) + "\n"


# Errors and their buckets ------------------------------------------------------------------------


@dataclass
class _Evidence:
    """What the debug data says about pages and lines, for guessing an error's bucket."""

    candidates: list[Candidate]
    index_pages: set[int]
    running: list[Line]
    image_only: set[int]
    flat: list[Section]
    window: int
    labels: LabelSettings

    def false_bucket(self, section: Section) -> str:
        """Why a line became a heading it is not, or a heading started on the wrong page."""
        line = next(
            (
                c.line
                for c in self.candidates
                if c.decision == "accept"
                and c.line.page == section.start_page
                and c.line.text == section.evidence
            ),
            None,
        )
        if section.start_page in self.index_pages or (line is not None and line.in_index_block):
            return "index_page"
        if section.start_page in self.image_only:
            return "ocr"
        before = self.flat[: self.flat.index(section)]
        if section.label != OTHER and any(
            o.label == section.label and section.start_page - o.start_page <= self.window
            for o in before
        ):
            return "repeat_title"
        if any(r.text.casefold() == section.evidence.casefold() for r in self.running):
            return "boilerplate"
        if _REFERENCE.search(section.evidence):
            return "cross_reference"
        return "mid_page" if section.starts_mid_page else "other"

    def missed_bucket(self, key: str, page: int) -> str:
        """Why a section was not found on its start page."""
        if page in self.image_only:
            return "ocr"
        mine = [c for c in self.candidates if c.line.page == page and key in (c.id_norm, c.label)]
        if mine:
            best = max(mine, key=lambda c: c.score)
            if best.score_breakdown.get("in_table_or_index", 0) < 0:
                return "index_page"
            if best.score_breakdown.get("repeat_title", 0) < 0:
                return "repeat_title"
            if not best.first_on_page:
                return "mid_page"
            return "level" if best.decision == "accept" else "other"  # accepted: too deep to emit
        if any(r.page == page and label_for_text(r.text, self.labels) == key for r in self.running):
            return "boilerplate"
        return "other"


def _errors(result: ExtractionResult, truth: Truth, settings: Settings) -> list[Error]:
    flat = list(_walk(result.sections))
    by_id = {s.id: s for s in flat}
    debug = result.debug
    evidence = _Evidence(
        candidates=debug.candidates if debug else [],
        index_pages={entry.page for entry in debug.index_entries} if debug else set(),
        running=debug.boilerplate_lines if debug else [],
        image_only=set(result.document.image_only_pages),
        flat=flat,
        window=settings.scoring.repeat_window_pages,
        labels=settings.labels,
    )
    errors = []
    for key, (start, _) in truth.sections.items():
        mine = by_id.get(key)
        if mine is None:
            errors.append(
                Error(evidence.missed_bucket(key, start), start, f"{key} (p{start}) not found")
            )
        elif mine.start_page != start:
            what = f"{key} starts on p{mine.start_page}, not p{start}"
            errors.append(Error(evidence.false_bucket(mine), mine.start_page, what))
    for s in flat:
        if s.id not in truth.sections:
            what = f"{s.id} on p{s.start_page} is no section: {s.evidence!r}"
            errors.append(Error(evidence.false_bucket(s), s.start_page, what))
    parents, truth_parents = _parents(result.sections), truth.parents()
    for key, level in truth.levels.items():
        mine = by_id.get(key)
        if mine is None or mine.start_page != truth.sections[key][0]:
            continue
        if mine.level != level:
            errors.append(
                Error("level", mine.start_page, f"{key} is level {mine.level}, not {level}")
            )
        elif parents[key] != truth_parents[key]:
            what = f"{key} hangs under {parents[key]}, not {truth_parents[key]}"
            errors.append(Error("level", mine.start_page, what))
    for label, span in truth.targets.items():
        got, status = result.targets.get(label), result.targets_status.get(label)
        if got == span and status == truth.status.get(label):
            continue
        source = result.targets_source.get(label)
        if any([s.start_page, s.end_page] == span for s in flat) or (
            source is not None and source.section in truth.sections
        ):
            bucket = "label"  # the section is there; the label went elsewhere
        elif truth.status.get(label) == "not_applicable" and status == "absent":
            bucket = "index_page"  # the index's Not Applicable listing was missed
        else:
            continue  # follows from a section error above
        page = span[0] if span else got[0] if got else None
        what = f"target {label} is {got} ({status}), not {span} ({truth.status.get(label)})"
        errors.append(Error(bucket, page, what))
    return errors


# Helpers -----------------------------------------------------------------------------------------


def _plain(mapping: dict[str, Any]) -> dict[str, Any]:
    """Without the "_comment" keys of the fixture files."""
    return {key: value for key, value in mapping.items() if not key.startswith("_")}


def _walk(sections: list[Section]) -> Iterator[Section]:
    for section in sections:
        yield section
        yield from _walk(section.children)


def _parents(sections: list[Section], parent: str | None = None) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for section in sections:
        found[section.id] = parent
        found |= _parents(section.children, section.id)
    return found


def _with(docs: list[DocumentScore], label: str) -> list[DocumentScore]:
    return [d for d in docs if label in d.targets]


def _sum(pairs: Iterable[tuple[int, int]]) -> tuple[int, int]:
    right = total = 0
    for a, b in pairs:
        right, total = right + a, total + b
    return right, total


def _share(right: int, total: int) -> float | None:
    return None if total == 0 else round(right / total, 3)


def _fraction(right: int, total: int) -> str:
    return "–" if total == 0 else f"{right}/{total} ({right / total:.0%})"


def _f1(docs: list[DocumentScore], level: int) -> float | None:
    right = sum(d.found[level][0] for d in docs)
    emitted = sum(d.found[level][1] for d in docs)
    expected = sum(d.found[level][2] for d in docs)
    if emitted + expected == 0:
        return None
    return round(2 * right / (emitted + expected), 3)  # = 2PR / (P + R)
