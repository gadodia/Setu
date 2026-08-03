"""Tests for the deterministic PDF extractor on generated synthetic statements."""

from __future__ import annotations

import pytest

from setu.synthetic.statements import generate_statements
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
