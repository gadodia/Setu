"""Grounded performance and portfolio attention signals."""

from decimal import Decimal

from sqlalchemy import select

from setu.models import Holding
from setu.extraction import ExtractedHolding, ExtractionResult, reconcile_holding_cost_basis
from setu.models import AssetClass, Geography
from setu.synthetic.generate import seed_portfolio
from setu.tools.calc import compute_net_worth
from setu.tools.insights import build_portfolio_insights, compute_investment_performance


def test_synthetic_roi_uses_only_source_stated_cost_basis(session, config):
    seed_portfolio(session, config)

    performance = compute_investment_performance(compute_net_worth(session, config))

    assert performance.status == "available"
    assert performance.current_value == Decimal("262135.200000000")
    assert performance.cost_basis == Decimal("183045.000000000")
    assert performance.unrealized_gain == Decimal("79090.200000000")
    assert performance.roi_fraction == (
        Decimal("79090.200000000") / Decimal("183045.000000000")
    )
    assert performance.coverage_fraction == Decimal("1")
    assert performance.covered_positions == 7
    assert performance.total_positions == 7


def test_insights_surface_concentration_currency_and_allocation_drift(session, config):
    seed_portfolio(session, config)

    insights = build_portfolio_insights(session, config)
    titles = {insight.title for insight in insights}

    assert "USD exposure exceeds your guardrail" in titles
    assert "Largest position: Apple Inc." in titles
    assert "Largest allocation drift: Equity" in titles


def test_missing_cost_basis_reduces_roi_coverage_without_estimation(session, config):
    seed_portfolio(session, config)
    holding = session.scalar(select(Holding).where(Holding.symbol == "VOO"))
    holding.cost_basis = None
    session.commit()

    performance = compute_investment_performance(compute_net_worth(session, config))
    insights = build_portfolio_insights(session, config)

    assert performance.covered_positions == 6
    assert performance.coverage_fraction < Decimal("1")
    assert any(insight.title == "ROI coverage is incomplete" for insight in insights)


def test_explicit_cas_invested_amount_overlays_a_model_omission():
    text = """Scheme Name Units Invested Amount NAV Current Value
Axis Bluechip Fund 15,000.000 900,000.00 80.0000 1,200,000.00
HDFC Corporate Bond Fund 8,000.000 600,000.00 80.0000 640,000.00"""
    result = ExtractionResult(holdings=[
        ExtractedHolding(
            name="Axis Bluechip Fund",
            asset_class=AssetClass.EQUITY,
            geography=Geography.INDIA,
            quantity="15000",
            market_value="1200000",
            currency="INR",
        ),
        ExtractedHolding(
            name="HDFC Corporate Bond Fund",
            asset_class=AssetClass.DEBT,
            geography=Geography.INDIA,
            quantity="8000",
            market_value="640000",
            currency="INR",
        ),
    ])

    reconciled = reconcile_holding_cost_basis(text, result)

    assert [holding.cost_basis for holding in reconciled.holdings] == ["900000.00", "600000.00"]


def test_cost_basis_is_cleared_when_source_has_no_cost_evidence():
    result = ExtractionResult(holdings=[
        ExtractedHolding(
            name="Example Fund",
            asset_class=AssetClass.EQUITY,
            geography=Geography.US,
            quantity="1",
            market_value="100",
            cost_basis="50",
            currency="USD",
        )
    ])

    reconciled = reconcile_holding_cost_basis("Example Fund 1 $100", result)

    assert reconciled.holdings[0].cost_basis is None
