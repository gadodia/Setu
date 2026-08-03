"""Tests for the tool registry: schemas well-formed + dispatch computes exact figures."""

from __future__ import annotations

from decimal import Decimal

import pytest

from setu.synthetic.generate import seed_portfolio
from setu.tools.registry import TOOL_SCHEMAS, build_executor


def test_schemas_wellformed():
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {"fx_convert", "compute_net_worth", "pdf_extract"}
    for t in TOOL_SCHEMAS:
        assert "description" in t and "input_schema" in t
        assert t["input_schema"]["type"] == "object"


def test_dispatch_fx_convert(session, config):
    dispatch = build_executor(session, config)
    out = dispatch("fx_convert", {"amount": 320000, "currency": "INR"})
    expected = Decimal("320000") * config.fx_rates["INR"]
    assert Decimal(out["converted"]) == expected
    assert out["base_currency"] == "USD"


def test_dispatch_net_worth_matches_ledger(session, config):
    seed_portfolio(session, config)
    dispatch = build_executor(session, config)
    out = dispatch("compute_net_worth", {})
    assert Decimal(out["net_worth"]) == Decimal("262413.3000000")
    # Allocation fractions should sum to ~1.
    total = sum(Decimal(v) for v in out["allocation_fractions"].values())
    assert abs(total - Decimal("1")) < Decimal("0.0000001")


def test_dispatch_unknown_tool_raises(session, config):
    dispatch = build_executor(session, config)
    with pytest.raises(ValueError):
        dispatch("nonexistent_tool", {})
