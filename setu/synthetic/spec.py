"""The canonical synthetic portfolio — defined ONCE, consumed by both the DB seeder and the
PDF statement renderer so the two can never diverge.

Persona: Setu's signature P2 (Cross-Border Professional / NRI) — holdings in both jurisdictions,
USD-heavy, mixed account types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from setu.models import AccountType, AssetClass, Geography, PolicyType

AS_OF = date(2026, 6, 30)


def D(x: str) -> Decimal:
    return Decimal(x)


@dataclass(frozen=True)
class HoldingSpec:
    symbol: str | None
    name: str
    asset_class: AssetClass
    geography: Geography
    quantity: Decimal
    market_value: Decimal   # native currency, as of AS_OF
    currency: str


@dataclass(frozen=True)
class PolicySpec:
    name: str
    policy_type: PolicyType
    asset_value: Decimal          # counts toward net worth (0 for TERM)
    currency: str
    sum_assured: Decimal | None = None


@dataclass(frozen=True)
class AccountSpec:
    institution: str
    geography: Geography
    account_name: str
    account_type: AccountType
    currency: str
    account_ref: str
    holdings: list[HoldingSpec] = field(default_factory=list)
    balance: Decimal | None = None
    policies: list[PolicySpec] = field(default_factory=list)


# --- The portfolio ---------------------------------------------------------------------------

PORTFOLIO: list[AccountSpec] = [
    AccountSpec(
        institution="Fidelity", geography=Geography.US,
        account_name="Individual Brokerage", account_type=AccountType.BROKERAGE,
        currency="USD", account_ref="****1234",
        holdings=[
            HoldingSpec("VOO", "Vanguard S&P 500 ETF", AssetClass.EQUITY, Geography.US,
                        D("120"), D("60000.00"), "USD"),
            HoldingSpec("AAPL", "Apple Inc.", AssetClass.EQUITY, Geography.US,
                        D("200"), D("44000.00"), "USD"),
            HoldingSpec("BND", "Vanguard Total Bond ETF", AssetClass.DEBT, Geography.US,
                        D("150"), D("11000.00"), "USD"),
        ],
    ),
    AccountSpec(
        institution="Fidelity", geography=Geography.US,
        account_name="401(k)", account_type=AccountType.RETIREMENT_401K,
        currency="USD", account_ref="****9012",
        holdings=[
            HoldingSpec("FXAIX", "Fidelity 500 Index", AssetClass.EQUITY, Geography.US,
                        D("300"), D("90000.00"), "USD"),
            HoldingSpec("FXNAX", "Fidelity US Bond Index", AssetClass.DEBT, Geography.US,
                        D("400"), D("20000.00"), "USD"),
        ],
    ),
    AccountSpec(
        institution="CAMS (Mutual Funds)", geography=Geography.INDIA,
        account_name="MF Folio", account_type=AccountType.MF_FOLIO,
        currency="INR", account_ref="****5678",
        holdings=[
            HoldingSpec(None, "Axis Bluechip Fund", AssetClass.EQUITY, Geography.INDIA,
                        D("15000.000"), D("1200000.00"), "INR"),
            HoldingSpec(None, "HDFC Corporate Bond Fund", AssetClass.DEBT, Geography.INDIA,
                        D("8000.000"), D("640000.00"), "INR"),
        ],
    ),
    AccountSpec(
        institution="HDFC Bank", geography=Geography.INDIA,
        account_name="Savings", account_type=AccountType.BANK,
        currency="INR", account_ref="****4321",
        balance=D("320000.00"),
    ),
    AccountSpec(
        institution="Tata AIA Life", geography=Geography.INDIA,
        account_name="Insurance", account_type=AccountType.INSURANCE,
        currency="INR", account_ref="****7777",
        policies=[
            PolicySpec("Tata AIA Fortune Pro (ULIP)", PolicyType.ULIP,
                       asset_value=D("950000.00"), currency="INR"),
            PolicySpec("Tata AIA Sampoorna Raksha (Term)", PolicyType.TERM,
                       asset_value=D("0.00"), currency="INR", sum_assured=D("10000000.00")),
        ],
    ),
]

# User-declared target risk profile (drives actual-vs-target, §0.4).
RISK_PROFILE = {
    "label": "aggressive-cross-border",
    "target_equity": D("0.70"),
    "target_debt": D("0.30"),
    "target_cash": D("0.00"),
    "max_usd_fraction": D("0.60"),
}
