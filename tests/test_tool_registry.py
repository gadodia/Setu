"""Tests for the tool registry: schemas well-formed + dispatch computes exact figures."""

from __future__ import annotations

from decimal import Decimal

import pytest

from setu.synthetic.generate import seed_portfolio
from setu.tools.registry import TOOL_SCHEMAS, build_executor


def test_schemas_wellformed():
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {"fx_convert", "compute_net_worth", "analyze_portfolio"}
    for t in TOOL_SCHEMAS:
        assert "description" in t and "input_schema" in t
        assert t["input_schema"]["type"] == "object"
    assert "path" not in str(TOOL_SCHEMAS).lower()
    assert "raw text" not in str(TOOL_SCHEMAS).lower()


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
    assert Decimal(out["net_worth"]) == Decimal("275488.500000000")
    # Allocation fractions should sum to ~1.
    total = sum(Decimal(v) for v in out["allocation_fractions"].values())
    assert abs(total - Decimal("1")) < Decimal("0.0000001")


def test_dispatch_portfolio_analysis_is_sanitized_and_source_backed(session, config):
    seed_portfolio(session, config)
    dispatch = build_executor(session, config)

    out = dispatch("analyze_portfolio", {})

    assert Decimal(out["performance"]["unrealized_gain"]) == Decimal("79090.200000000")
    assert "USD exposure exceeds your guardrail" in {
        insight["title"] for insight in out["insights"]
    }
    assert "raw_text" not in str(out)
    assert "path" not in str(out)
    assert out["health"]["label"] == "Needs attention"
    assert out["health"]["horizons"]["short_term"]["status"] == "elevated"
    assert "suitability assessment" in out["limitations"]


def test_dispatch_unknown_tool_raises(session, config):
    dispatch = build_executor(session, config)
    with pytest.raises(ValueError):
        dispatch("nonexistent_tool", {})
