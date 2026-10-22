"""System prompts and answer schemas for stage 7 and the whole-document fallback (SPEC §7, §9)."""

from __future__ import annotations

from typing import Any

ADJUDICATE_SYSTEM = """\
You decide whether a line is the heading that starts a NEW section of a tender document.

Each candidate comes with its page, the accepted headings around it, what the document's own \
index lists, and the text that follows it on the page.

- A line in a table of contents, an annexure list, a checklist cell, or a cross-reference inside \
a sentence is NOT a section start.
- A label on the tender's cover page (such as "PART–I: UNPRICED BID" or "(Domestic Open Tender)") \
is NOT a section start.
- A title repeated on the cover page or second page of a section that already started is NOT a \
new section.
- An unnumbered title that continues the previous annexure is NOT a new section unless the \
document's index lists it.

Decide every candidate: accept or reject. As evidence, copy a short passage exactly as it appears \
in that candidate's page text (when you accept, the heading line itself). Give your confidence \
from 0 to 1 and the reason in one sentence."""

ADJUDICATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate": {"type": "integer"},
                    "decision": {"type": "string", "enum": ["accept", "reject"]},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["candidate", "decision", "evidence", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["decisions"],
    "additionalProperties": False,
}

WHOLE_DOC_SYSTEM = """\
You rebuild the section structure of a tender document whose automatic extraction failed the \
checks named in the request.

You get every page as <<PAGE n>> with the start of its text and the heading-like lines found on \
it, the document's own index, and the current result. List every section start, in document \
order, with:
- page: the page the section starts on;
- id: the id as printed ("Annexure 19", "B", "Part II"), or "" when the heading has none;
- title: the heading's title;
- level: 1 for a top-level section, 2 for an annexure, 3 for "Annexure 2.1", 4 for "Annexure 2.6.1";
- evidence: the heading line, copied exactly from that page.

Do not list a section that only the index mentions: it must start on a page you were shown. Do \
not give end pages; they are computed from the starts."""

WHOLE_DOC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer"},
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "level": {"type": "integer"},
                    "evidence": {"type": "string"},
                },
                "required": ["page", "id", "title", "level", "evidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}
