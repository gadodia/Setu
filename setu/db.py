"""Database session management and ingestion dedup helpers.

Two dedup mechanisms back the idempotent, time-aware ingestion described in ARCHITECTURE.md §2a:
  1. statement-hash lookup   — skip a file we've already processed (idempotency)
  2. latest-per-account query — value each account from its newest snapshot (temporal validity)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from setu.config import Config, load_config
from setu.models import Base, Statement

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _init_engine(config: Config):
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(config.db_url, future=True)
        _SessionLocal = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine


def get_session(config: Config | None = None) -> Session:
    """Return a new Session (engine is created lazily on first call)."""
    config = config or load_config()
    _init_engine(config)
    assert _SessionLocal is not None
    return _SessionLocal()


def create_all(config: Config | None = None) -> None:
    """Create all tables and apply small SQLite compatibility upgrades.

    Setu is still a local single-user application and does not carry a migration framework. The
    compatibility step keeps an existing ledger usable when additive source-control columns are
    introduced; it never drops or rewrites user records.
    """
    config = config or load_config()
    engine = _init_engine(config)
    Base.metadata.create_all(engine)
    _ensure_compatibility_columns(engine)


def _ensure_compatibility_columns(engine: Engine) -> None:
    """Add source-control columns to an existing SQLite ledger without deleting data."""
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        statement_columns = {
            column["name"] for column in inspector.get_columns("statements")
        }
        if "is_active" not in statement_columns:
            connection.exec_driver_sql(
                "ALTER TABLE statements "
                "ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
            )

        if inspector.has_table("holdings"):
            holding_columns = {
                column["name"] for column in inspector.get_columns("holdings")
            }
            if "cost_basis" not in holding_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE holdings ADD COLUMN cost_basis NUMERIC(18, 4)"
                )

        obligation_columns = {
            column["name"] for column in inspector.get_columns("obligations")
        }
        if "statement_id" not in obligation_columns:
            connection.exec_driver_sql(
                "ALTER TABLE obligations "
                "ADD COLUMN statement_id INTEGER REFERENCES statements(id)"
            )

        if inspector.has_table("ingestion_runs"):
            run_columns = {
                column["name"] for column in inspector.get_columns("ingestion_runs")
            }
            if "persisted_balances" not in run_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE ingestion_runs "
                    "ADD COLUMN persisted_balances INTEGER NOT NULL DEFAULT 0"
                )

        # Older imported policy premiums pre-date Obligation.statement_id. Recover the link only
        # when account + deterministic description identify exactly one source. Ambiguous legacy
        # rows remain unlinked and active instead of risking exclusion with the wrong document.
        connection.exec_driver_sql(
            """
            UPDATE obligations
               SET statement_id = (
                   SELECT MIN(insurance_policies.statement_id)
                     FROM insurance_policies
                    WHERE insurance_policies.account_id = obligations.account_id
                      AND obligations.description = 'Premium: ' || insurance_policies.policy_name
                      AND insurance_policies.statement_id IS NOT NULL
               )
             WHERE obligations.statement_id IS NULL
               AND 1 = (
                   SELECT COUNT(DISTINCT insurance_policies.statement_id)
                     FROM insurance_policies
                    WHERE insurance_policies.account_id = obligations.account_id
                      AND obligations.description = 'Premium: ' || insurance_policies.policy_name
                      AND insurance_policies.statement_id IS NOT NULL
               )
            """
        )


def drop_all(config: Config | None = None) -> None:
    config = config or load_config()
    engine = _init_engine(config)
    Base.metadata.drop_all(engine)


# --- Dedup helper #1: statement-level idempotency (§2a) --------------------------------------

def file_sha256(path: str | Path) -> str:
    """SHA-256 of a file's raw bytes — the idempotency key for a statement."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def statement_already_ingested(session: Session, file_hash: str) -> bool:
    """True if a statement with this content hash is already in the ledger (→ skip re-processing)."""
    return session.query(Statement).filter(Statement.file_hash == file_hash).first() is not None
