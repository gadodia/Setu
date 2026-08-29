"""Isolated final-demo ledger setup.

The demo database is deliberately separate from ``data/setu.db`` so a clean rehearsal never
deletes or changes the user's imported records.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from setu.config import Config, load_config
from setu.db import _ensure_compatibility_columns, file_sha256
from setu.models import Account, Base, InsurancePolicy, Obligation, Statement
from setu.synthetic.generate import seed_portfolio, write_ground_truth
from setu.synthetic.spec import AS_OF, PORTFOLIO
from setu.synthetic.statements import generate_statements


@dataclass(frozen=True)
class DemoRuntime:
    config: Config
    sessions: sessionmaker[Session]
    checkpoint_path: Path


def prepare_demo(config: Config | None = None, *, reset: bool = False) -> DemoRuntime:
    """Create or refresh an isolated synthetic ledger and return its dependencies."""
    base = config or load_config()
    demo_config = base.model_copy(deep=True)
    demo_config.paths.db_path = demo_config.paths.data_dir / "setu-demo.db"
    checkpoint_path = demo_config.paths.data_dir / "setu-demo-checkpoints.db"

    engine = create_engine(demo_config.db_url, future=True)
    if reset:
        Base.metadata.drop_all(engine)
        checkpoint_path.unlink(missing_ok=True)
    Base.metadata.create_all(engine)
    _ensure_compatibility_columns(engine)
    sessions = sessionmaker(bind=engine, future=True, expire_on_commit=False)

    statement_paths = generate_statements(demo_config)
    with sessions() as session:
        has_accounts = (session.scalar(select(func.count()).select_from(Account)) or 0) > 0
        if not has_accounts:
            seed_portfolio(session, demo_config)
            _attach_demo_sources(session, statement_paths)

    write_ground_truth(demo_config)
    return DemoRuntime(
        config=demo_config,
        sessions=sessions,
        checkpoint_path=checkpoint_path,
    )


def _attach_demo_sources(session: Session, statement_paths: list[Path]) -> None:
    """Give seeded records realistic provenance and exact hashes for duplicate detection."""
    for account_spec, path in zip(PORTFOLIO, statement_paths, strict=True):
        account = session.scalar(
            select(Account)
            .where(Account.account_ref == account_spec.account_ref)
            .join(Account.institution)
        )
        if account is None:
            continue
        statement = Statement(
            institution=account_spec.institution,
            account_ref=account_spec.account_ref,
            file_name=path.name,
            file_hash=file_sha256(path),
            period_end=AS_OF,
        )
        session.add(statement)
        session.flush()
        for record in (*account.holdings, *account.balances, *account.policy_values):
            record.statement_id = statement.id
        for record in session.scalars(
            select(InsurancePolicy).where(InsurancePolicy.account_id == account.id)
        ).all():
            record.statement_id = statement.id
        for record in session.scalars(
            select(Obligation).where(Obligation.account_id == account.id)
        ).all():
            record.statement_id = statement.id
    session.commit()
