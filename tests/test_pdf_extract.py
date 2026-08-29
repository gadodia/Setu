"""Tests for the deterministic PDF extractor on generated synthetic statements."""

from __future__ import annotations

import pytest
from reportlab.pdfgen import canvas

from setu.synthetic.statements import generate_statements
from setu.tools import pdf_extract
from setu.tools.pdf_extract import extract


@pytest.fixture
def statements(config):
    return generate_statements(config)


def test_generates_all_statements(statements):
    names = {p.name for p in statements}
    assert "fidelity_brokerage.pdf" in names
    assert "cams_mf_folio.pdf" in names
    assert "hdfc_bank_bank.pdf" in names
    assert "tata_aia_life_insurance.pdf" in names


def test_brokerage_text_and_tables(config, statements):
    path = config.paths.synthetic_dir / "fidelity_brokerage.pdf"
    doc = extract(path)

    # Text carries the holdings.
    assert "VOO" in doc.full_text
    assert "Apple Inc." in doc.full_text
    assert "60,000.00" in doc.full_text

    # A structured holdings table is recovered.
    assert doc.all_tables, "expected at least one table"
    header = doc.all_tables[0][0]
    assert "Symbol" in header and "Market Value" in header


def test_cas_statement_has_nav_column(config, statements):
    path = config.paths.synthetic_dir / "cams_mf_folio.pdf"
    doc = extract(path)
    assert "Axis Bluechip Fund" in doc.full_text
    assert "NAV" in doc.full_text


def test_missing_pdf_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract(tmp_path / "nope.pdf")


def _image_only_pdf(path):
    """A page with vector artwork but no embedded text, representative of a scan."""
    c = canvas.Canvas(str(path))
    c.rect(72, 600, 450, 120, fill=0)
    c.save()


class FakeOcrEngine:
    model_name = "fake-paddleocr-vl"

    def __init__(self, result=None):
        self.calls = 0
        self.result = result

    def recognize(self, image):
        self.calls += 1
        return self.result


def test_scanned_page_uses_ocr_fallback_and_preserves_evidence(tmp_path):
    OcrResult = getattr(pdf_extract, "OcrResult", None)
    OcrBlock = getattr(pdf_extract, "OcrBlock", None)
    assert OcrResult is not None and OcrBlock is not None

    path = tmp_path / "scanned-policy.pdf"
    _image_only_pdf(path)
    engine = FakeOcrEngine(OcrResult(
        text="LIC Policy Number 1234\nCurrent Surrender Value INR 245000",
        blocks=[OcrBlock(
            bbox=(10.0, 20.0, 300.0, 60.0),
            label="text",
            text="Current Surrender Value INR 245000",
        )],
    ))

    doc = extract(path, ocr_engine=engine, ocr_mode="auto", min_text_chars=20)

    assert engine.calls == 1
    assert doc.pages[0].source == "ocr"
    assert doc.pages[0].ocr_model == "fake-paddleocr-vl"
    assert "245000" in doc.full_text
    assert doc.pages[0].ocr_blocks[0].bbox == (10.0, 20.0, 300.0, 60.0)


def test_native_text_fast_path_does_not_load_ocr(config, statements):
    engine = FakeOcrEngine()
    path = config.paths.synthetic_dir / "fidelity_brokerage.pdf"

    doc = extract(path, ocr_engine=engine, ocr_mode="auto", min_text_chars=20)

    assert engine.calls == 0
    assert all(page.source == "embedded" for page in doc.pages)


def test_ocr_can_be_disabled_for_scanned_pages(tmp_path):
    path = tmp_path / "scanned-policy.pdf"
    _image_only_pdf(path)
    engine = FakeOcrEngine()

    doc = extract(path, ocr_engine=engine, ocr_mode="never")

    assert engine.calls == 0
    assert doc.full_text == ""


def test_empty_ocr_result_fails_closed(tmp_path):
    OcrResult = getattr(pdf_extract, "OcrResult", None)
    OcrError = getattr(pdf_extract, "OcrError", RuntimeError)
    assert OcrResult is not None

    path = tmp_path / "scanned-policy.pdf"
    _image_only_pdf(path)
    engine = FakeOcrEngine(OcrResult(text="", blocks=[]))

    with pytest.raises(OcrError, match="no text"):
        extract(path, ocr_engine=engine, ocr_mode="auto", min_text_chars=20)
