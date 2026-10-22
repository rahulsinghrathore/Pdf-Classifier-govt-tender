"""Scripted answers for FakeLLMClient, which stands in for the LLM in tests (no network), and a
scripted OCR engine, which stands in for tesseract."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from tender_sections.ocr import OCRWord

_SHOWN = re.compile(r'^Candidate line: "(.*)"   \[', re.MULTILINE)


def shown(request: dict[str, Any]) -> list[str]:
    """The candidate lines of an adjudication request, in order."""
    return _SHOWN.findall(request["user"])


def verdict(
    decision: str, *, evidence: str | None = None, confidence: float = 0.9
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """The same decision for every candidate shown; the evidence is the line itself by default."""

    def answer(request: dict[str, Any]) -> dict[str, Any]:
        return {
            "decisions": [
                {
                    "candidate": n,
                    "decision": decision,
                    "evidence": evidence if evidence is not None else line,
                    "confidence": confidence,
                    "reason": "scripted",
                }
                for n, line in enumerate(shown(request), 1)
            ]
        }

    return answer


@dataclass
class FakeOCREngine:
    """OCR in tests: `read` gets each rendered page and returns its words, or raises."""

    read: Callable[[Image.Image], list[OCRWord]]
    sizes: list[tuple[int, int]] = field(default_factory=list)  # each page image it was given

    def words(self, image: Image.Image) -> list[OCRWord]:
        self.sizes.append(image.size)
        return self.read(image)


def printed(*lines: tuple[str, float, float, float], block: int = 1) -> list[OCRWord]:
    """Words of (text, x, y, height) lines as an engine would box them: line ids (block, 1, n)."""
    words = []
    for number, (text, x, y, height) in enumerate(lines, 1):
        for word in text.split():
            width = 0.5 * height * len(word)
            words.append(OCRWord(word, x, y, width, height, (block, 1, number)))
            x += width + 0.3 * height
    return words
