"""Tests for §2a: latest-snapshot-per-account wins, and statement-hash idempotency."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from setu.db import statement_already_ingested
from setu.models import (
    Account,
    AccountType,
    AssetClass,
    Geography,
    Holding,
    Institution,
    Statement,
)
from setu.tools import calc


def _account(session) -> Account:
    inst = Institution(name="Fidelity", geography=Geography.US)
    acct = Account(institution=inst, name="Brokerage",
                   account_type=AccountType.BROKERAGE, currency="USD")
    session.add_all([inst, acct])
    session.commit()
    return acct


def test_latest_snapshot_supersedes_stale(session, config):
    """Two snapshots of the same holding at different dates → only the newer counts."""
    acct = _account(session)
    session.add_all([
        Holding(account=acct, symbol="VOO", name="Vanguard S&P 500",
                asset_class=AssetClass.EQUITY, geography=Geography.US,
                market_value=Decimal("180000.00"), currency="USD", as_of_date=date(2026, 1, 31)),
        Holding(account=acct, symbol="VOO", name="Vanguard S&P 500",
                asset_class=AssetClass.EQUITY, geography=Geography.US,
                market_value=Decimal("214000.00"), currency="USD", as_of_date=date(2026, 3, 31)),
    ])
    session.commit()

    nw = calc.compute_net_worth(session, config)
    # Must be the March value, NOT the sum (394000) and NOT the stale Jan value.
    assert nw.total == Decimal("214000.00")


def test_multiple_positions_same_date_all_kept(session, config):
    """An account holds many positions at once — all at the max date must be kept."""
    acct = _account(session)
    session.add_all([
        Holding(account=acct, symbol="VOO", name="VOO", asset_class=AssetClass.EQUITY,
                geography=Geography.US, market_value=Decimal("100000"), currency="USD",
                as_of_date=date(2026, 3, 31)),
        Holding(account=acct, symbol="AAPL", name="AAPL", asset_class=AssetClass.EQUITY,
                geography=Geography.US, market_value=Decimal("50000"), currency="USD",
                as_of_date=date(2026, 3, 31)),
    ])
    session.commit()

    nw = calc.compute_net_worth(session, config)
    assert nw.total == Decimal("150000")


def test_statement_hash_idempotency(session, config):
    """A seen file_hash is detected so ingestion can skip re-processing."""
    stmt = Statement(institution="Fidelity", account_ref="****1234",
                     file_name="fid_2026_06.pdf", file_hash="abc123",
                     period_end=date(2026, 6, 30))
    session.add(stmt)
    session.commit()

    assert statement_already_ingested(session, "abc123") is True
    assert statement_already_ingested(session, "never-seen") is False
