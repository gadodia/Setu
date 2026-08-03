"""Seed the ledger from the canonical portfolio spec, and write the ground-truth fixture.

This is the Week 1 keystone: it seeds a realistic mix of US and Indian assets whose correct net
worth and allocation are computable up front, then writes a ground-truth JSON fixture. The
golden-file tests assert that `calc.compute_net_worth` reproduces these numbers exactly — proving
the deterministic substrate is correct before any LLM is added.

Numbers come from `spec.PORTFOLIO` (shared with the PDF statement renderer) so the DB seed and
the synthetic documents can never diverge.
"""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from setu.config import Config, load_config
from setu.models import (
    Account,
    Balance,
    Holding,
    Institution,
    PolicyValue,
    RiskProfile,
)
from setu.synthetic.spec import AS_OF, PORTFOLIO, RISK_PROFILE


def seed_portfolio(session: Session, config: Config | None = None) -> None:
    """Populate the ledger with the synthetic US+India portfolio (from spec.PORTFOLIO)."""
    config = config or load_config()

    # One Institution row per distinct (name, geography).
    institutions: dict[str, Institution] = {}
    for acct_spec in PORTFOLIO:
        if acct_spec.institution not in institutions:
            institutions[acct_spec.institution] = Institution(
                name=acct_spec.institution, geography=acct_spec.geography
            )

    for acct_spec in PORTFOLIO:
        account = Account(
            institution=institutions[acct_spec.institution],
            name=acct_spec.account_name,
            account_type=acct_spec.account_type,
            currency=acct_spec.currency,
            account_ref=acct_spec.account_ref,
        )
        session.add(account)

        for h in acct_spec.holdings:
            session.add(Holding(
                account=account, symbol=h.symbol, name=h.name,
                asset_class=h.asset_class, geography=h.geography,
                quantity=h.quantity, market_value=h.market_value,
                currency=h.currency, as_of_date=AS_OF,
            ))

        if acct_spec.balance is not None:
            session.add(Balance(
                account=account, amount=acct_spec.balance,
                currency=acct_spec.currency, as_of_date=AS_OF,
            ))

        for p in acct_spec.policies:
            session.add(PolicyValue(
                account=account, policy_name=p.name, policy_type=p.policy_type,
                sum_assured=p.sum_assured, asset_value=p.asset_value,
                currency=p.currency, as_of_date=AS_OF,
            ))

    session.add(RiskProfile(**RISK_PROFILE))
    session.commit()


def write_ground_truth(config: Config | None = None) -> dict:
    """Compute expected totals independently (simple summation over the spec) and write JSON.

    Deliberately computed by a *different* path than calc.compute_net_worth, so the golden-file
    test compares two independent derivations of the same numbers.
    """
    config = config or load_config()
    fx = {"USD": Decimal("1"), "INR": config.fx_rates["INR"]}

    by_asset_class: dict[str, Decimal] = {}
    by_geography: dict[str, Decimal] = {}
    by_currency: dict[str, Decimal] = {}

    def add(bucket: dict, key: str, value: Decimal):
        bucket[key] = bucket.get(key, Decimal("0")) + value

    for acct in PORTFOLIO:
        for h in acct.holdings:
            base_val = h.market_value * fx[h.currency]
            add(by_asset_class, h.asset_class.value, base_val)
            add(by_geography, h.geography.value, base_val)
            add(by_currency, h.currency.upper(), base_val)
        if acct.balance is not None:
            base_val = acct.balance * fx[acct.currency]
            add(by_asset_class, "CASH", base_val)
            add(by_geography, acct.geography.value, base_val)
            add(by_currency, acct.currency.upper(), base_val)
        for p in acct.policies:
            if p.asset_value > 0:
                base_val = p.asset_value * fx[p.currency]
                add(by_asset_class, "INSURANCE_CASH_VALUE", base_val)
                add(by_geography, acct.geography.value, base_val)
                add(by_currency, p.currency.upper(), base_val)

    total = sum(by_asset_class.values(), Decimal("0"))

    ground_truth = {
        "base_currency": config.base_currency,
        "as_of": AS_OF.isoformat(),
        "total": str(total),
        "by_asset_class": {k: str(v) for k, v in by_asset_class.items()},
        "by_geography": {k: str(v) for k, v in by_geography.items()},
        "by_currency": {k: str(v) for k, v in by_currency.items()},
        "notes": "Term policy (sum assured 1,00,00,000 INR) excluded from net worth by design.",
    }

    out_path = config.paths.synthetic_dir / "ground_truth.json"
    out_path.write_text(json.dumps(ground_truth, indent=2))
    return ground_truth
