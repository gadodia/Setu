"""Deterministic PDF → text/tables extraction (pdfplumber).

This tool does NO interpretation — it turns a PDF into raw text and table rows. The LLM layer
(Week 2 extraction) reads this output and produces structured holdings; the split keeps the
"machine reads bytes, model interprets meaning" boundary clean, and makes extraction testable
without a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber


@dataclass
class ExtractedPage:
    page_number: int
    text: str
    tables: list[list[list[str | None]]] = field(default_factory=list)


@dataclass
class ExtractedDoc:
    path: str
    pages: list[ExtractedPage] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """All page text concatenated — the primary input to the LLM extractor."""
        return "\n\n".join(p.text for p in self.pages)

    @property
    def all_tables(self) -> list[list[list[str | None]]]:
        return [t for p in self.pages for t in p.tables]


def extract(path: str | Path) -> ExtractedDoc:
    """Extract text + tables from every page of a PDF."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such PDF: {path}")

    doc = ExtractedDoc(path=str(path))
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            doc.pages.append(ExtractedPage(
                page_number=i,
                text=page.extract_text() or "",
                tables=page.extract_tables() or [],
            ))
    return doc
