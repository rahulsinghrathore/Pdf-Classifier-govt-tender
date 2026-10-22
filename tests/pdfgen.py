"""Tiny synthetic PDFs, so ingest and boilerplate rules are testable without the fixture PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pymupdf

A4 = (595.0, 842.0)
A3_LANDSCAPE = (1191.0, 842.0)


class Item(Protocol):
    def draw(self, page: pymupdf.Page) -> None: ...


@dataclass
class Text:
    x: float
    y: float  # baseline, points from the top edge
    text: str
    size: float = 10
    bold: bool = False

    def draw(self, page: pymupdf.Page) -> None:
        font = "hebo" if self.bold else "helv"
        page.insert_text((self.x, self.y), self.text, fontsize=self.size, fontname=font)


@dataclass
class Image:
    rect: tuple[float, float, float, float]

    def draw(self, page: pymupdf.Page) -> None:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
        pix.clear_with(128)
        page.insert_image(pymupdf.Rect(self.rect), pixmap=pix)


@dataclass
class Grid:
    """Ruled table of rows × cols cells with its top-left corner at (x, y)."""

    x: float
    y: float
    cell_w: float
    cell_h: float
    rows: int
    cols: int

    def draw(self, page: pymupdf.Page) -> None:
        for row in range(self.rows):
            for col in range(self.cols):
                x0, y0 = self.x + col * self.cell_w, self.y + row * self.cell_h
                rect = pymupdf.Rect(x0, y0, x0 + self.cell_w, y0 + self.cell_h)
                page.draw_rect(rect, color=(0, 0, 0), width=0.5)


@dataclass
class Rows:
    """A ruled table: one rectangle per cell, with the cell's text inside it."""

    x: float
    y: float
    rows: list[tuple[str, ...]]
    widths: tuple[float, ...] = (140, 320)
    height: float = 20
    size: float = 9

    def draw(self, page: pymupdf.Page) -> None:
        for r, cells in enumerate(self.rows):
            x = self.x
            for width, text in zip(self.widths, (*cells, *[""] * len(self.widths)), strict=False):
                rect = pymupdf.Rect(
                    x, self.y + r * self.height, x + width, self.y + (r + 1) * self.height
                )
                page.draw_rect(rect, color=(0, 0, 0), width=0.5)
                if text:
                    page.insert_text(
                        (x + 4, rect.y1 - 6), text, fontsize=self.size, fontname="helv"
                    )
                x += width


def paragraph(y: float, lines: int = 6, size: float = 10) -> list[Text]:
    """Ordinary body text, enough to give the document a body size."""
    text = "a paragraph of ordinary body text " * 2
    return [Text(72, y + i * (size + 4), text, size=size) for i in range(lines)]


@dataclass
class Strokes:
    """`count` separate vector paths: a stand-in for a CAD drawing with no raster image."""

    count: int

    def draw(self, page: pymupdf.Page) -> None:
        for i in range(self.count):
            page.draw_line((60, 120 + i * 8), (520, 140 + i * 8))


def header(text: str, y: float = 40.0, **kwargs) -> Text:
    return Text(72, y, text, **kwargs)


def footer(text: str, y: float = 815.0, **kwargs) -> Text:
    return Text(72, y, text, **kwargs)


def make_pdf(pages: list[list[Item]], size: tuple[float, float] = A4) -> bytes:
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page(width=size[0], height=size[1])
        for item in items:
            item.draw(page)
    data = doc.tobytes()
    doc.close()
    return data
