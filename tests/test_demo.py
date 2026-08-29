"""Final-demo setup is isolated from the personal ledger."""

from decimal import Decimal

from sqlalchemy import func, select

from setu.demo import prepare_demo
from setu.models import InsurancePolicy, Obligation, Statement
from setu.tools.calc import compute_net_worth
from setu.tools.insights import compute_investment_performance, compute_portfolio_health


def test_demo_setup_uses_separate_seeded_database(config):
    personal_path = config.paths.db_path

    runtime = prepare_demo(config, reset=True)

    assert runtime.config.paths.db_path != personal_path
    assert runtime.config.paths.db_path.name == "setu-demo.db"
    assert personal_path.exists() is False
    with runtime.sessions() as session:
        net_worth = compute_net_worth(session, runtime.config)
        performance = compute_investment_performance(net_worth)
        health = compute_portfolio_health(session, runtime.config, net_worth=net_worth)
        source_count = session.scalar(select(func.count()).select_from(Statement))
        policy_count = session.scalar(select(func.count()).select_from(InsurancePolicy))
        obligation_count = session.scalar(select(func.count()).select_from(Obligation))
    assert net_worth.total == Decimal("275488.500000000")
    assert performance.unrealized_gain == Decimal("79090.200000000")
    assert health.score == 37
    assert health.label == "Needs attention"
    assert {key: value.status for key, value in health.horizons.items()} == {
        "current": "elevated",
        "short_term": "elevated",
        "long_term": "elevated",
    }
    assert {component.key: component.score for component in health.components} == {
        "allocation": 5,
        "concentration": 5,
        "currency": 1,
        "liquidity": 8,
        "data": 18,
    }
    assert source_count == 6
    assert policy_count == 3
    assert obligation_count == 3
    assert len(health.actions) == 5
    assert any("essential expenses" in item for item in health.missing_data)
