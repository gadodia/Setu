"""Net worth and allocation — the deterministic core.

Reads the ledger, converts every position to the base currency via `fx`, and aggregates:
  - net worth
  - allocation by asset class, geography, and currency

All math is exact Decimal. Positions are valued at the figure stated in their source statement,
using the *latest* snapshot per account (temporal validity, §2a). Term policies contribute 0.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from setu.config import Config, load_config
from setu.models import (
    AssetClass,
    Balance,
    Geography,
    Holding,
    PolicyValue,
    Statement,
)
from setu.tools import fx


@dataclass
class Position:
    """A single valued line, normalized to the base currency."""

    label: str
    asset_class: AssetClass
    geography: Geography
    currency: str
    native_value: Decimal
    base_value: Decimal
    native_cost_basis: Decimal | None
    base_cost_basis: Decimal | None
    kind: str
    account_id: int
    statement_id: int | None


@dataclass
class NetWorth:
    base_currency: str
    total: Decimal
    positions: list[Position] = field(default_factory=list)
    by_asset_class: dict[str, Decimal] = field(default_factory=dict)
    by_geography: dict[str, Decimal] = field(default_factory=dict)
    by_currency: dict[str, Decimal] = field(default_factory=dict)

    def allocation(self, buckets: dict[str, Decimal]) -> dict[str, Decimal]:
        """Convert a bucket of base-currency totals into fractions of net worth."""
        if self.total == 0:
            return {k: Decimal("0") for k in buckets}
        return {k: (v / self.total) for k, v in buckets.items()}


def _latest_by_account(rows, as_of_attr: str = "as_of_date"):
    """Keep every row at the newest as_of_date *per account* (temporal validity, §2a).

    A new statement supersedes prior snapshots for that account, so we drop older dates —
    but an account holds many positions at once, so we keep *all* rows tied at its max date,
    not a single row.
    """
    max_date: dict[int, object] = {}
    for r in rows:
        d = getattr(r, as_of_attr)
        if r.account_id not in max_date or d > max_date[r.account_id]:
            max_date[r.account_id] = d
    return [r for r in rows if getattr(r, as_of_attr) == max_date[r.account_id]]


def _active_rows(session: Session, model):
    """Return rows whose source is active; unlinked manual/synthetic rows remain included."""
    source_id = model.statement_id
    query = (
        select(model)
        .outerjoin(Statement, source_id == Statement.id)
        .where(or_(source_id.is_(None), Statement.is_active.is_(True)))
    )
    return session.scalars(query).all()


def compute_net_worth(session: Session, config: Config | None = None) -> NetWorth:
    """Aggregate the whole ledger into a base-currency net-worth + allocation view."""
    config = config or load_config()
    base = config.base_currency

    positions: list[Position] = []

    # Holdings — latest snapshot per account.
    for h in _latest_by_account(_active_rows(session, Holding)):
        positions.append(
            Position(
                label=h.name or h.symbol or "holding",
                asset_class=h.asset_class,
                geography=h.geography,
                currency=h.currency,
                native_value=h.market_value,
                base_value=fx.convert(h.market_value, h.currency, config),
                native_cost_basis=h.cost_basis,
                base_cost_basis=(
                    None if h.cost_basis is None else fx.convert(h.cost_basis, h.currency, config)
                ),
                kind="holding",
                account_id=h.account_id,
                statement_id=h.statement_id,
            )
        )

    # Bank balances — latest per account, always CASH.
    for b in _latest_by_account(_active_rows(session, Balance)):
        acct = b.account
        positions.append(
            Position(
                label=f"{acct.institution.name} cash" if acct and acct.institution else "cash",
                asset_class=AssetClass.CASH,
                geography=acct.institution.geography if acct and acct.institution else Geography.US,
                currency=b.currency,
                native_value=b.amount,
                base_value=fx.convert(b.amount, b.currency, config),
                native_cost_basis=None,
                base_cost_basis=None,
                kind="balance",
                account_id=b.account_id,
                statement_id=b.statement_id,
            )
        )

    # Policy values — latest per account; asset_value already excludes TERM (=0).
    for p in _latest_by_account(_active_rows(session, PolicyValue)):
        if p.asset_value and p.asset_value > 0:
            acct = p.account
            positions.append(
                Position(
                    label=p.policy_name,
                    asset_class=AssetClass.INSURANCE_CASH_VALUE,
                    geography=acct.institution.geography if acct and acct.institution else Geography.INDIA,
                    currency=p.currency,
                    native_value=p.asset_value,
                    base_value=fx.convert(p.asset_value, p.currency, config),
                    native_cost_basis=None,
                    base_cost_basis=None,
                    kind="insurance",
                    account_id=p.account_id,
                    statement_id=p.statement_id,
                )
            )

    total = sum((p.base_value for p in positions), Decimal("0"))

    by_asset_class: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_geography: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for p in positions:
        by_asset_class[p.asset_class.value] += p.base_value
        by_geography[p.geography.value] += p.base_value
        by_currency[p.currency.upper()] += p.base_value

    return NetWorth(
        base_currency=base,
        total=total,
        positions=positions,
        by_asset_class=dict(by_asset_class),
        by_geography=dict(by_geography),
        by_currency=dict(by_currency),
    )
