"""Synthetic heading candidates for the pure-function stages: levels, assemble, validate."""

from __future__ import annotations

from tender_sections.models import Candidate, Line


def heading(
    page: int,
    kind: str = "named",
    *,
    id: str | None = None,
    id_norm: str | None = None,
    display_id: str | None = None,
    title: str = "",
    label: str = "other",
    first: bool = True,
    y: float = 0.1,
    size: float = 12.0,
    level: int | None = None,
    decision: str = "accept",
    source: str = "same_line",
    score: int = 10,
) -> Candidate:
    """A candidate as stages 4–6 would leave it; named ids default to annexures."""
    if kind == "named":
        id_norm = id_norm or f"annexure_{(id or '').replace('.', '_')}"
        display_id = display_id or f"Annexure {id}"
    elif kind == "letter":
        id_norm, display_id = id_norm or f"sec_{id}", display_id or id
    elif kind == "numeric":
        id_norm, display_id = id_norm or f"clause_{(id or '').replace('.', '_')}", display_id or id
    text = f"{display_id or ''} {title}".strip()
    line = Line(
        page=page,
        text=text,
        x0=0.1,
        y0=y,
        x1=0.6,
        y1=y + 0.02,
        font_size=size,
        bold_ratio=1.0,
        caps_ratio=0.0,
        order=int(y * 100),
    )
    return Candidate(
        line=line,
        kind=kind,
        id=id,
        id_norm=id_norm,
        display_id=display_id or "",
        title=title,
        title_source=source,
        label=label,
        first_on_page=first,
        score=score,
        decision=decision,
        decided_by=None if decision == "undecided" else "rules",
        level=level,
    )
