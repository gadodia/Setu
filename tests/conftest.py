"""Shared test fixtures — an isolated ledger per test, never the real data/setu.db."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from setu.config import Config, load_config
from setu.models import Base


@pytest.fixture
def config(tmp_path) -> Config:
    """A real config but with paths redirected into a temp dir (isolated DB + fixtures)."""
    cfg = load_config()
    # Copy so we don't mutate the cached singleton for other tests.
    cfg = cfg.model_copy(deep=True)
    cfg.paths.data_dir = tmp_path
    cfg.paths.synthetic_dir = tmp_path / "synthetic"
    cfg.paths.inbox_dir = tmp_path / "inbox"
    cfg.paths.db_path = tmp_path / "test.db"
    cfg.dashboard_password = SecretStr("setu-test-password")
    cfg.resolve_paths()
    return cfg


@pytest.fixture
def session(config) -> Session:
    """An in-memory SQLite session with the schema created."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def D():
    return Decimal
