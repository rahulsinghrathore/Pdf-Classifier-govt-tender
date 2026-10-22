"""Stage 8: the section tree and its page ranges (SPEC §8). The LLM never computes end pages.

A section ends where the next heading outside its own subtree starts: on the page before, or on
that same page when the heading starts mid-page. The subtree, not the level, decides: an orphan
Annexure 7.2 (there is no Annexure 7) keeps its level 3 but hangs under the level-1 section, so it
ends Annexure 6 at f1 p31; a rule by level alone would run Annexure 6 on to p34. The exclusive
range applies the same rule to the next heading of any level, so a parent stops at its first child.
"""

from __future__ import annotations

from dataclasses import dataclass

from tender_sections.labels import OTHER
from tender_sections.levels import keyword
from tender_sections.models import Candidate, Section


@dataclass
class Assembly:
    sections: list[Section]  # the tree
    flat: list[Section]  # the same sections in document order
    headings: list[Candidate]  # the heading behind each entry of `flat`
    flat_inclusive: dict[str, list[int]]
    flat_exclusive: dict[str, list[int]]
    unassigned_pages: list[int]


def assemble(headings: list[Candidate], page_count: int) -> Assembly:
    """Headings must carry a level; see levels.assign_levels and levels.emitted."""
    order = sorted(headings, key=lambda h: (h.line.page, h.line.y0))
    parents = _parents(order)
    last_descendant = list(range(len(order)))
    for j in range(len(order)):
        parent = parents[j]
        while parent is not None:
            last_descendant[parent] = j
            parent = parents[parent]

    def end_before(k: int) -> int:
        if k >= len(order):
            return page_count
        nxt = order[k]
        return nxt.line.page if not nxt.first_on_page else nxt.line.page - 1

    keys = _keys(order)
    flat = [
        Section(
            id=keys[i],
            display_id=h.display_id,
            title=h.title,
            label=h.label,
            level=h.level or 0,
            start_page=h.line.page,
            end_page=end_before(last_descendant[i] + 1),
            end_page_exclusive=end_before(i + 1),
            starts_mid_page=not h.first_on_page,
            confidence=h.confidence if h.confidence is not None else round(h.score / 10, 2),
            decided_by=h.decided_by or "rules",
            evidence=h.line.text,
            bbox=(h.line.x0, h.line.y0, h.line.x1, h.line.y1),
        )
        for i, h in enumerate(order)
    ]
    roots: list[Section] = []
    for i, parent in enumerate(parents):
        (roots if parent is None else flat[parent].children).append(flat[i])
    for section in flat:
        assert section.start_page <= section.end_page_exclusive <= section.end_page, section.id
        assert not section.children or section.end_page == _last(section).end_page, section.id

    covered = {
        page
        for section in flat
        if section.level == 1
        for page in range(section.start_page, section.end_page + 1)
    }
    return Assembly(
        sections=roots,
        flat=flat,
        headings=order,
        flat_inclusive={s.id: [s.start_page, s.end_page] for s in flat},
        flat_exclusive={s.id: [s.start_page, s.end_page_exclusive] for s in flat},
        unassigned_pages=[page for page in range(1, page_count + 1) if page not in covered],
    )


def _parents(order: list[Candidate]) -> list[int | None]:
    """Parent index of each heading.

    The nearest open heading of a lower level, except for a dotted named id ("Annexure 3.2"),
    which hangs under its deepest existing ancestor id, or, as an orphan, under the nearest
    heading that is not of its family (the level-1 section).
    """
    parents: list[int | None] = []
    stack: list[int] = []
    for j, heading in enumerate(order):
        while stack and (order[stack[-1]].level or 0) >= (heading.level or 0):
            stack.pop()
        if heading.kind == "named" and "." in (heading.id or ""):
            ancestors = [k for k in stack if _id_ancestor(order[k], heading)]
            if ancestors:
                while stack[-1] != ancestors[-1]:
                    stack.pop()
            else:
                while stack and _family(order[stack[-1]]) == _family(heading):
                    stack.pop()
        parents.append(stack[-1] if stack else None)
        stack.append(j)
    return parents


def _family(heading: Candidate) -> str | None:
    return keyword(heading) if heading.kind == "named" else None


def _id_ancestor(candidate: Candidate, heading: Candidate) -> bool:
    if _family(candidate) != _family(heading) or candidate.id is None or heading.id is None:
        return False
    mine, theirs = candidate.id.split("."), heading.id.split(".")
    return len(mine) < len(theirs) and theirs[: len(mine)] == mine


def _keys(order: list[Candidate]) -> list[str]:
    """Level 1: the canonical label ("pqc"), else the id ("sec_B"). Named: the id_norm."""
    keys: list[str] = []
    used: dict[str, int] = {}
    for h in order:
        if h.level == 1 and h.label != OTHER:
            key = h.label
        elif h.id_norm is not None:
            key = h.id_norm
        else:
            key = f"p{h.line.page}_{h.label if h.label != OTHER else 'heading'}"
        used[key] = used.get(key, 0) + 1
        keys.append(key if used[key] == 1 else f"{key}_{used[key]}")
    return keys


def _last(section: Section) -> Section:
    while section.children:
        section = section.children[-1]
    return section
