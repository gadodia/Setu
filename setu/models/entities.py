"""The ledger entities.

Enums are stored as plain strings (SQLAlchemy ``Enum``) for readability in the DB and easy
extension. Every monetary column uses the ``Money`` type (Decimal); quantities use ``Quantity``.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from setu.models.base import Base, Money, Quantity


# --- Enums (controlled vocabularies) ---------------------------------------------------------

class Geography(str, enum.Enum):
    US = "US"
    INDIA = "INDIA"


class AccountType(str, enum.Enum):
    # US
    BROKERAGE = "BROKERAGE"
    RETIREMENT_401K = "401K"
    IRA = "IRA"
    # India
    DEMAT = "DEMAT"
    MF_FOLIO = "MF_FOLIO"
    # Shared
    BANK = "BANK"
    INSURANCE = "INSURANCE"


class AssetClass(str, enum.Enum):
    EQUITY = "EQUITY"
    DEBT = "DEBT"
    CASH = "CASH"
    INSURANCE_CASH_VALUE = "INSURANCE_CASH_VALUE"
    REAL_ASSET = "REAL_ASSET"


class PolicyType(str, enum.Enum):
    TERM = "TERM"              # pure protection — no asset value
    ENDOWMENT = "ENDOWMENT"    # surrender / maturity value
    ULIP = "ULIP"             # fund value = units x NAV


# --- Core entities ---------------------------------------------------------------------------

class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    geography: Mapped[Geography] = mapped_column(Enum(Geography))

    accounts: Mapped[list["Account"]] = relationship(back_populates="institution")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    name: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType))
    currency: Mapped[str] = mapped_column(String(3))          # ISO 4217, e.g. USD / INR
    # Redacted/masked identifier only — raw account numbers never persist to the ledger.
    account_ref: Mapped[str | None] = mapped_column(String(64), default=None)

    institution: Mapped["Institution"] = relationship(back_populates="accounts")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="account")
    balances: Mapped[list["Balance"]] = relationship(back_populates="account")
    policy_values: Mapped[list["PolicyValue"]] = relationship(back_populates="account")


class Holding(Base):
    """A position in a security/fund, valued at the figure stated in its source statement."""

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    statement_id: Mapped[int | None] = mapped_column(ForeignKey("statements.id"), default=None)

    symbol: Mapped[str | None] = mapped_column(String(32), default=None)
    name: Mapped[str] = mapped_column(String(160), default="")
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass))
    geography: Mapped[Geography] = mapped_column(Enum(Geography))

    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"))
    # market_value is in the account's native currency, as of `as_of_date`.
    market_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    # Total document-backed acquisition cost/invested amount. Null means the source did not state
    # it, so Setu must not manufacture an ROI for this position.
    cost_basis: Mapped[Decimal | None] = mapped_column(Money, default=None)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    as_of_date: Mapped[date] = mapped_column(Date)

    account: Mapped["Account"] = relationship(back_populates="holdings")


class PolicyValue(Base):
    """Insurance policy valuation — semantics from the KB, numbers from documents (§5b).

    Term policies contribute no asset value (coverage only); endowment uses surrender/maturity
    value; ULIP uses fund value. `asset_value` is what counts toward net worth (0 for TERM).
    """

    __tablename__ = "policy_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    statement_id: Mapped[int | None] = mapped_column(ForeignKey("statements.id"), default=None)

    policy_name: Mapped[str] = mapped_column(String(160))
    policy_type: Mapped[PolicyType] = mapped_column(Enum(PolicyType))

    sum_assured: Mapped[Decimal | None] = mapped_column(Money, default=None)   # coverage (TERM)
    asset_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))  # counts to net worth
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    as_of_date: Mapped[date] = mapped_column(Date)

    account: Mapped["Account"] = relationship(back_populates="policy_values")


class InsurancePolicy(Base):
    """The policy contract itself, separate from optional point-in-time cash value."""

    __tablename__ = "insurance_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    statement_id: Mapped[int | None] = mapped_column(ForeignKey("statements.id"), default=None)
    policy_name: Mapped[str] = mapped_column(String(160), default="Unknown policy")
    policy_type: Mapped[PolicyType] = mapped_column(Enum(PolicyType))
    plan_number: Mapped[str | None] = mapped_column(String(32), default=None)
    status: Mapped[str | None] = mapped_column(String(40), default=None)
    sum_assured: Mapped[Decimal | None] = mapped_column(Money, default=None)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    commencement_date: Mapped[date | None] = mapped_column(Date, default=None)
    maturity_date: Mapped[date | None] = mapped_column(Date, default=None)
    policy_term_years: Mapped[int | None] = mapped_column(Integer, default=None)
    premium_payment_term_years: Mapped[int | None] = mapped_column(Integer, default=None)
    premium_amount: Mapped[Decimal | None] = mapped_column(Money, default=None)
    premium_due_date: Mapped[date | None] = mapped_column(Date, default=None)
    premium_mode: Mapped[str | None] = mapped_column(String(24), default=None)
    vested_bonus: Mapped[Decimal | None] = mapped_column(Money, default=None)
    guaranteed_additions: Mapped[Decimal | None] = mapped_column(Money, default=None)
    stated_maturity_value: Mapped[Decimal | None] = mapped_column(Money, default=None)
    maturity_benefit_4pct: Mapped[Decimal | None] = mapped_column(Money, default=None)
    maturity_benefit_8pct: Mapped[Decimal | None] = mapped_column(Money, default=None)
    document_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    evidence_status: Mapped[str] = mapped_column(String(24), default="partial")
    current_value_status: Mapped[str] = mapped_column(String(24), default="not_provided")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped["Account"] = relationship()


class Balance(Base):
    """A point-in-time cash balance for an account (bank / sweep)."""

    __tablename__ = "balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    statement_id: Mapped[int | None] = mapped_column(ForeignKey("statements.id"), default=None)

    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    as_of_date: Mapped[date] = mapped_column(Date)

    account: Mapped["Account"] = relationship(back_populates="balances")


class Obligation(Base):
    """A commitment against wealth — insurance premium, loan EMI — with a due date."""

    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), default=None)
    statement_id: Mapped[int | None] = mapped_column(ForeignKey("statements.id"), default=None)
    description: Mapped[str] = mapped_column(String(160), default="")
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    recurring: Mapped[bool] = mapped_column(default=False)


class FxRate(Base):
    """A currency's value in the base currency, as of a date (audit of rates actually used)."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("currency", "as_of_date", name="uq_fx_currency_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(3))
    rate_to_base: Mapped[Decimal] = mapped_column(Money)   # value of 1 unit in base currency
    as_of_date: Mapped[date] = mapped_column(Date)


class RiskProfile(Base):
    """The user-declared target allocation that drives the actual-vs-target feedback loop (§0.4)."""

    __tablename__ = "risk_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(80), default="default")

    # Target allocation by asset class, as fractions summing to ~1.0.
    target_equity: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.70"))
    target_debt: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.30"))
    target_cash: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))

    # Currency guardrail, e.g. max 0.60 of net worth in USD.
    max_usd_fraction: Mapped[Decimal | None] = mapped_column(Money, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Statement(Base):
    """A source document. `file_hash` + the uniqueness constraint make ingestion idempotent (§2a)."""

    __tablename__ = "statements"
    __table_args__ = (
        UniqueConstraint("institution", "account_ref", "period_end", name="uq_statement_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    institution: Mapped[str] = mapped_column(String(120))
    account_ref: Mapped[str | None] = mapped_column(String(64), default=None)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)   # SHA-256 of the raw file
    period_end: Mapped[date] = mapped_column(Date)                    # = as_of_date of its contents
    # Source control is reversible: inactive statements and all records linked to them remain in
    # the ledger for provenance, but are excluded from portfolio views and calculations.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IngestionRun(Base):
    """Sanitized UI workflow metadata; uploaded document bytes are never stored here."""

    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(80), unique=True)
    source_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    document_kind: Mapped[str | None] = mapped_column(String(24), default=None)
    reconcile_status: Mapped[str | None] = mapped_column(String(24), default=None)
    question: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    persisted_holdings: Mapped[int] = mapped_column(Integer, default=0)
    persisted_balances: Mapped[int] = mapped_column(Integer, default=0)
    persisted_policies: Mapped[int] = mapped_column(Integer, default=0)
    persisted_obligations: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Transaction(Base):
    """Secondary: cash-flow signal only (savings rate). Not a headline feature."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    statement_id: Mapped[int | None] = mapped_column(ForeignKey("statements.id"), default=None)
    txn_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
