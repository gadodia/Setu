"""Database session management and ingestion dedup helpers.

Two dedup mechanisms back the idempotent, time-aware ingestion described in ARCHITECTURE.md §2a:
  1. statement-hash lookup   — skip a file we've already processed (idempotency)
  2. latest-per-account query — value each account from its newest snapshot (temporal validity)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import create_engine
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
    """Create all tables. Idempotent — safe to call repeatedly."""
    config = config or load_config()
    engine = _init_engine(config)
    Base.metadata.create_all(engine)


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
