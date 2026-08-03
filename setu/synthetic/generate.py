"""Generate a synthetic cross-border (US + India) portfolio with KNOWN totals.

This is the Week 1 keystone: it seeds the ledger with a realistic mix of US and Indian assets
whose correct net worth and allocation are computable up front, then writes a ground-truth JSON
fixture. The golden-file tests assert that `calc.compute_net_worth` reproduces these numbers
exactly — proving the deterministic substrate is correct before any LLM is added.

The persona modeled here is Setu's signature P2 (Cross-Border Professional / NRI): meaningful
holdings in both jurisdictions, USD-heavy, mixed account types.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from setu.config import Config, load_config
from setu.models import (
    Account,
    AccountType,
    AssetClass,
    Balance,
    Geography,
    Holding,
    Institution,
    PolicyType,
    PolicyValue,
    RiskProfile,
)

AS_OF = date(2026, 6, 30)


def _d(x: str) -> Decimal:
    return Decimal(x)


def seed_portfolio(session: Session, config: Config | None = None) -> None:
    """Populate the ledger with the synthetic US+India portfolio."""
    config = config or load_config()

    # --- US: Fidelity brokerage (USD equity) ---
    fidelity = Institution(name="Fidelity", geography=Geography.US)
    fid_brokerage = Account(
        institution=fidelity,
        name="Individual Brokerage",
        account_type=AccountType.BROKERAGE,
        currency="USD",
        account_ref="****1234",
    )
    session.add_all([
        Holding(account=fid_brokerage, symbol="VOO", name="Vanguard S&P 500 ETF",
                asset_class=AssetClass.EQUITY, geography=Geography.US,
                quantity=_d("120"), market_value=_d("60000.00"), currency="USD", as_of_date=AS_OF),
        Holding(account=fid_brokerage, symbol="AAPL", name="Apple Inc.",
                asset_class=AssetClass.EQUITY, geography=Geography.US,
                quantity=_d("200"), market_value=_d("44000.00"), currency="USD", as_of_date=AS_OF),
        Holding(account=fid_brokerage, symbol="BND", name="Vanguard Total Bond ETF",
                asset_class=AssetClass.DEBT, geography=Geography.US,
                quantity=_d("150"), market_value=_d("11000.00"), currency="USD", as_of_date=AS_OF),
    ])

    # --- US: 401(k) (USD equity + debt) ---
    fid_401k = Account(
        institution=fidelity, name="401(k)", account_type=AccountType.RETIREMENT_401K,
        currency="USD", account_ref="****9012",
    )
    session.add_all([
        Holding(account=fid_401k, symbol="FXAIX", name="Fidelity 500 Index",
                asset_class=AssetClass.EQUITY, geography=Geography.US,
                quantity=_d("300"), market_value=_d("90000.00"), currency="USD", as_of_date=AS_OF),
        Holding(account=fid_401k, symbol="FXNAX", name="Fidelity US Bond Index",
                asset_class=AssetClass.DEBT, geography=Geography.US,
                quantity=_d("400"), market_value=_d("20000.00"), currency="USD", as_of_date=AS_OF),
    ])

    # --- India: CAMS mutual funds (INR equity + debt) ---
    cams = Institution(name="CAMS (Mutual Funds)", geography=Geography.INDIA)
    mf_folio = Account(
        institution=cams, name="MF Folio", account_type=AccountType.MF_FOLIO,
        currency="INR", account_ref="****5678",
    )
    session.add_all([
        Holding(account=mf_folio, name="Axis Bluechip Fund",
                asset_class=AssetClass.EQUITY, geography=Geography.INDIA,
                quantity=_d("15000.000"), market_value=_d("1200000.00"), currency="INR", as_of_date=AS_OF),
        Holding(account=mf_folio, name="HDFC Corporate Bond Fund",
                asset_class=AssetClass.DEBT, geography=Geography.INDIA,
                quantity=_d("8000.000"), market_value=_d("640000.00"), currency="INR", as_of_date=AS_OF),
    ])

    # --- India: HDFC bank balance (INR cash) ---
    hdfc = Institution(name="HDFC Bank", geography=Geography.INDIA)
    hdfc_savings = Account(
        institution=hdfc, name="Savings", account_type=AccountType.BANK,
        currency="INR", account_ref="****4321",
    )
    session.add(Balance(account=hdfc_savings, amount=_d("320000.00"), currency="INR", as_of_date=AS_OF))

    # --- India: Tata AIA insurance (a ULIP with asset value + a TERM plan with none) ---
    tata = Institution(name="Tata AIA Life", geography=Geography.INDIA)
    tata_acct = Account(
        institution=tata, name="Insurance", account_type=AccountType.INSURANCE,
        currency="INR", account_ref="****7777",
    )
    session.add_all([
        PolicyValue(account=tata_acct, policy_name="Tata AIA Fortune Pro (ULIP)",
                    policy_type=PolicyType.ULIP, asset_value=_d("950000.00"),
                    currency="INR", as_of_date=AS_OF),
        # Term plan: coverage only, NO asset value — must not count toward net worth.
        PolicyValue(account=tata_acct, policy_name="Tata AIA Sampoorna Raksha (Term)",
                    policy_type=PolicyType.TERM, sum_assured=_d("10000000.00"),
                    asset_value=_d("0.00"), currency="INR", as_of_date=AS_OF),
    ])

    # --- User-declared target risk profile (drives actual-vs-target, §0.4) ---
    session.add(RiskProfile(
        label="aggressive-cross-border",
        target_equity=_d("0.70"), target_debt=_d("0.30"), target_cash=_d("0.00"),
        max_usd_fraction=_d("0.60"),
    ))

    session.commit()


def write_ground_truth(config: Config | None = None) -> dict:
    """Compute the expected totals independently and write them to a JSON fixture.

    Computed here from the same inputs but by simple summation, so the test has an
    *independent* expected value to compare `calc` against.
    """
    config = config or load_config()
    usd = Decimal("1")
    inr = config.fx_rates["INR"]

    # Base-currency (USD) values.
    us_equity = _d("60000") + _d("44000") + _d("90000")            # 194000
    us_debt = _d("11000") + _d("20000")                            # 31000
    in_equity = _d("1200000") * inr                                # INR → USD
    in_debt = _d("640000") * inr
    in_cash = _d("320000") * inr
    in_ins = _d("950000") * inr

    by_asset_class = {
        "EQUITY": us_equity * usd + in_equity,
        "DEBT": us_debt * usd + in_debt,
        "CASH": in_cash,
        "INSURANCE_CASH_VALUE": in_ins,
    }
    total = sum(by_asset_class.values(), Decimal("0"))

    by_geography = {
        "US": (us_equity + us_debt) * usd,
        "INDIA": in_equity + in_debt + in_cash + in_ins,
    }
    by_currency = {
        "USD": (us_equity + us_debt) * usd,
        "INR": in_equity + in_debt + in_cash + in_ins,
    }

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
