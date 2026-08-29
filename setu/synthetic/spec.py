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

AS_OF = date(2026, 8, 15)


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
    cost_basis: Decimal     # source-stated total cost / invested amount
    currency: str


@dataclass(frozen=True)
class PolicySpec:
    name: str
    policy_type: PolicyType
    asset_value: Decimal | None   # current value only when explicitly stated
    currency: str
    sum_assured: Decimal | None = None
    plan_number: str | None = None
    premium_amount: Decimal | None = None
    premium_due_date: date | None = None
    premium_mode: str | None = None
    commencement_date: date | None = None
    maturity_date: date | None = None
    policy_term_years: int | None = None
    evidence_status: str = "complete"


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
                        D("120"), D("60000.00"), D("48000.00"), "USD"),
            HoldingSpec("AAPL", "Apple Inc.", AssetClass.EQUITY, Geography.US,
                        D("320"), D("80000.00"), D("32000.00"), "USD"),
            HoldingSpec("BND", "Vanguard Total Bond ETF", AssetClass.DEBT, Geography.US,
                        D("150"), D("10000.00"), D("11000.00"), "USD"),
        ],
    ),
    AccountSpec(
        institution="Fidelity", geography=Geography.US,
        account_name="401(k)", account_type=AccountType.RETIREMENT_401K,
        currency="USD", account_ref="****9012",
        holdings=[
            HoldingSpec("FXAIX", "Fidelity 500 Index", AssetClass.EQUITY, Geography.US,
                        D("240"), D("70000.00"), D("55000.00"), "USD"),
            HoldingSpec("FXNAX", "Fidelity US Bond Index", AssetClass.DEBT, Geography.US,
                        D("400"), D("20000.00"), D("19000.00"), "USD"),
        ],
    ),
    AccountSpec(
        institution="CAMS (Mutual Funds)", geography=Geography.INDIA,
        account_name="MF Folio", account_type=AccountType.MF_FOLIO,
        currency="INR", account_ref="****5678",
        holdings=[
            HoldingSpec(None, "Axis Bluechip Fund", AssetClass.EQUITY, Geography.INDIA,
                        D("15000.000"), D("1200000.00"), D("900000.00"), "INR"),
            HoldingSpec(None, "HDFC Corporate Bond Fund", AssetClass.DEBT, Geography.INDIA,
                        D("8000.000"), D("640000.00"), D("600000.00"), "INR"),
        ],
    ),
    AccountSpec(
        institution="HDFC Bank", geography=Geography.INDIA,
        account_name="Savings", account_type=AccountType.BANK,
        currency="INR", account_ref="****4321",
        balance=D("160000.00"),
    ),
    AccountSpec(
        institution="Tata AIA Life", geography=Geography.INDIA,
        account_name="Insurance", account_type=AccountType.INSURANCE,
        currency="INR", account_ref="****7777",
        policies=[
            PolicySpec("Tata AIA Fortune Pro (ULIP)", PolicyType.ULIP,
                       asset_value=D("950000.00"), currency="INR",
                       sum_assured=D("2500000.00"), premium_amount=D("120000.00"),
                       premium_due_date=date(2026, 11, 15), premium_mode="Yearly",
                       commencement_date=date(2021, 11, 15),
                       maturity_date=date(2041, 11, 15), policy_term_years=20),
            PolicySpec("Tata AIA Sampoorna Raksha (Term)", PolicyType.TERM,
                       asset_value=None, currency="INR", sum_assured=D("10000000.00"),
                       premium_amount=D("30000.00"), premium_due_date=date(2027, 1, 15),
                       premium_mode="Yearly", commencement_date=date(2022, 1, 15),
                       maturity_date=date(2047, 1, 15), policy_term_years=25),
        ],
    ),
    AccountSpec(
        institution="LIC of India", geography=Geography.INDIA,
        account_name="Insurance", account_type=AccountType.INSURANCE,
        currency="INR", account_ref="****2468",
        policies=[
            PolicySpec("LIC New Jeevan Anand", PolicyType.ENDOWMENT,
                       asset_value=None, currency="INR", sum_assured=D("1500000.00"),
                       plan_number="915", premium_amount=D("60000.00"),
                       premium_due_date=date(2026, 9, 30), premium_mode="Yearly",
                       commencement_date=date(2018, 9, 30),
                       maturity_date=date(2038, 9, 30), policy_term_years=20,
                       evidence_status="partial"),
        ],
    ),
]

# User-declared target risk profile (drives actual-vs-target, §0.4).
RISK_PROFILE = {
    "label": "growth-with-reserve",
    "target_equity": D("0.65"),
    "target_debt": D("0.25"),
    "target_cash": D("0.10"),
    "max_usd_fraction": D("0.60"),
}
