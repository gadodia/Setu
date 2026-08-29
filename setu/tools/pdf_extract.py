"""PDF → text/tables extraction with a local OCR fallback for scanned pages.

Embedded text remains the deterministic fast path. Pages without enough embedded text are rendered
locally and passed to PaddleOCR-VL. OCR only transcribes page content; the downstream extraction and
valuation layers still validate and interpret financial fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any, Literal, Protocol

import pdfplumber


class OcrError(RuntimeError):
    """OCR could not safely produce text for a page that requires it."""


class OcrUnavailableError(OcrError):
    """The configured local OCR runtime is not installed."""


@dataclass
class OcrBlock:
    """One OCR layout block retained as evidence for later review."""

    bbox: tuple[float, float, float, float] | None
    label: str
    text: str


@dataclass
class OcrResult:
    text: str
    blocks: list[OcrBlock] = field(default_factory=list)


class OcrEngine(Protocol):
    model_name: str

    def recognize(self, image: Any) -> OcrResult: ...


class PaddleOcrVlEngine:
    """Lazy adapter for the full local PaddleOCR-VL document-parsing pipeline."""

    model_name = "PaddleOCR-VL"

    def __init__(self, pipeline_version: str = "v1"):
        self.pipeline_version = pipeline_version
        self._pipeline = None

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        # Avoid a network connectivity probe on every run. Model files are still downloaded from
        # the official source on first use, then loaded from PaddleX's local cache.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCRVL
        except ImportError as exc:
            raise OcrUnavailableError(
                "PaddleOCR-VL is required for scanned PDFs. Install it with "
                "`uv sync --extra ocr`; model weights download locally on first use."
            ) from exc
        try:
            self._pipeline = PaddleOCRVL(pipeline_version=self.pipeline_version)
        except Exception as exc:
            raise OcrUnavailableError(f"Could not initialize PaddleOCR-VL: {exc}") from exc
        return self._pipeline

    def recognize(self, image: Any) -> OcrResult:
        try:
            import numpy as np

            outputs = list(self._load().predict(np.asarray(image)))
        except OcrError:
            raise
        except Exception as exc:
            raise OcrError(f"PaddleOCR-VL inference failed: {exc}") from exc

        text_parts: list[str] = []
        blocks: list[OcrBlock] = []
        for output in outputs:
            markdown = getattr(output, "markdown", {}) or {}
            markdown_text = markdown.get("markdown_texts", "")
            if isinstance(markdown_text, (list, tuple)):
                markdown_text = "\n".join(str(part) for part in markdown_text)
            if str(markdown_text).strip():
                text_parts.append(str(markdown_text).strip())

            payload = getattr(output, "json", {}) or {}
            root = payload.get("res", payload) if isinstance(payload, dict) else {}
            for block in root.get("parsing_res_list", []) or []:
                content = str(block.get("block_content", "")).strip()
                bbox = _bbox_tuple(block.get("block_bbox"))
                blocks.append(OcrBlock(
                    bbox=bbox,
                    label=str(block.get("block_label", "unknown")),
                    text=content,
                ))

        if not text_parts and blocks:
            text_parts = [block.text for block in blocks if block.text]
        return OcrResult(text="\n".join(text_parts).strip(), blocks=blocks)


@dataclass
class ExtractedPage:
    page_number: int
    text: str
    tables: list[list[list[str | None]]] = field(default_factory=list)
    source: Literal["embedded", "ocr"] = "embedded"
    ocr_model: str | None = None
    ocr_blocks: list[OcrBlock] = field(default_factory=list)


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


def extract(
    path: str | Path,
    *,
    ocr_engine: OcrEngine | None = None,
    ocr_mode: Literal["auto", "always", "never"] = "auto",
    min_text_chars: int = 20,
    ocr_dpi: int = 200,
    ocr_pipeline_version: str = "v1",
) -> ExtractedDoc:
    """Extract text and tables, using local OCR only when a page needs it.

    ``min_text_chars`` counts non-whitespace characters. In ``auto`` mode a page below that
    threshold is treated as scanned/image-only. OCR failures are explicit and never converted into
    an apparently valid empty document.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such PDF: {path}")
    if ocr_mode not in ("auto", "always", "never"):
        raise ValueError(f"Unsupported OCR mode: {ocr_mode}")
    if min_text_chars < 0:
        raise ValueError("min_text_chars cannot be negative")

    doc = ExtractedDoc(path=str(path))
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            embedded_text = page.extract_text() or ""
            needs_ocr = ocr_mode == "always" or (
                ocr_mode == "auto" and _visible_char_count(embedded_text) < min_text_chars
            )
            if needs_ocr:
                engine = ocr_engine or PaddleOcrVlEngine(pipeline_version=ocr_pipeline_version)
                try:
                    image = page.to_image(resolution=ocr_dpi).original.convert("RGB")
                    result = engine.recognize(image)
                except OcrError:
                    raise
                except Exception as exc:
                    raise OcrError(f"Could not OCR page {i} of {path.name}: {exc}") from exc
                if not result.text.strip():
                    raise OcrError(
                        f"PaddleOCR-VL returned no text for page {i} of {path.name}; "
                        "ingestion stopped for review."
                    )
                text = result.text
                source: Literal["embedded", "ocr"] = "ocr"
                model = engine.model_name
                blocks = result.blocks
            else:
                text = embedded_text
                source = "embedded"
                model = None
                blocks = []
            doc.pages.append(ExtractedPage(
                page_number=i,
                text=text,
                tables=page.extract_tables() or [],
                source=source,
                ocr_model=model,
                ocr_blocks=blocks,
            ))
    return doc


def _visible_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _bbox_tuple(value: Any) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    try:
        numbers = tuple(float(number) for number in value)
    except (TypeError, ValueError):
        return None
    return numbers if len(numbers) == 4 else None
