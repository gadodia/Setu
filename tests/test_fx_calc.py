"""Golden-file tests: computed net worth/allocation must equal the known ground truth EXACTLY.

This is the Week 1 proof that the deterministic substrate is correct — and, once the LLM is
added, that it is not silently doing the math.
"""

from __future__ import annotations

from decimal import Decimal

from setu.synthetic.generate import seed_portfolio, write_ground_truth
from setu.tools import calc, fx


def test_fx_convert_base_is_identity(config):
    assert fx.convert(Decimal("100"), "USD", config) == Decimal("100")


def test_fx_convert_inr(config):
    # 1 INR = config rate in USD.
    expected = Decimal("320000") * config.fx_rates["INR"]
    assert fx.convert(Decimal("320000"), "INR", config) == expected


def test_fx_unknown_currency_raises(config):
    import pytest

    with pytest.raises(fx.FxError):
        fx.rate_to_base("EUR", config)


def test_net_worth_matches_ground_truth(session, config):
    seed_portfolio(session, config)
    gt = write_ground_truth(config)

    nw = calc.compute_net_worth(session, config)

    assert nw.total == Decimal(gt["total"]), "net worth must match ground truth exactly"


def test_asset_class_allocation_matches_ground_truth(session, config):
    seed_portfolio(session, config)
    gt = write_ground_truth(config)

    nw = calc.compute_net_worth(session, config)

    for cls, expected in gt["by_asset_class"].items():
        assert nw.by_asset_class[cls] == Decimal(expected), f"{cls} mismatch"


def test_geography_and_currency_allocation_match(session, config):
    seed_portfolio(session, config)
    gt = write_ground_truth(config)

    nw = calc.compute_net_worth(session, config)

    for geo, expected in gt["by_geography"].items():
        assert nw.by_geography[geo] == Decimal(expected), f"geo {geo} mismatch"
    for cur, expected in gt["by_currency"].items():
        assert nw.by_currency[cur] == Decimal(expected), f"currency {cur} mismatch"


def test_term_policy_excluded_from_net_worth(session, config):
    """A term policy has coverage but NO asset value — it must not inflate net worth."""
    seed_portfolio(session, config)
    nw = calc.compute_net_worth(session, config)

    # No position should be labeled as the term plan.
    labels = [p.label for p in nw.positions]
    assert not any("Term" in l for l in labels), "term policy must not be a net-worth position"


def test_allocations_sum_to_one(session, config):
    seed_portfolio(session, config)
    nw = calc.compute_net_worth(session, config)

    total_fraction = sum(nw.allocation(nw.by_asset_class).values(), Decimal("0"))
    assert abs(total_fraction - Decimal("1")) < Decimal("0.0000001")
