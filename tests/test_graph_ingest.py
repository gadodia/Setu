"""Week 3 — the LangGraph ingestion runtime, end to end with a FAKE local model.

These tests exercise the real graph (ingest → reconcile → conditional edge → persist / ask_user),
the SQLite checkpointer (interrupt + resume), and idempotency — without needing Ollama. The
IngestionAgent is replaced by a fake that returns fixed holdings + the real statement text, so
reconciliation runs against a genuine synthetic PDF's stated total.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from setu.agents.ingestion_agent import IngestionResult
from setu.agents.orchestrator import Orchestrator
from setu.extraction import ExtractedHolding
from setu.graph.build import build_graph
from setu.graph.nodes import Nodes
from setu.models import AssetClass, Base, Geography, Holding, Statement
from setu.synthetic.statements import generate_statements


def _holding(symbol, name, cls, geo, qty, mv, ccy):
    return ExtractedHolding(
        symbol=symbol, name=name, asset_class=cls, geography=geo,
        quantity=str(qty), market_value=str(mv), currency=ccy,
    )


class FakeIngestionAgent:
    """Returns fixed holdings + the real statement text (so reconcile sees the true stated total)."""

    def __init__(self, path: str, holdings, file_hash="hash-abc"):
        from setu.tools.pdf_extract import extract
        self._text = extract(path).full_text
        self._holdings = holdings
        self._file_hash = file_hash

    def run(self, path: str, run_date=None) -> IngestionResult:
        return IngestionResult(
            institution="Fidelity Investments",
            account_ref="****1234",
            period_end=date(2026, 6, 30),
            currency="USD",
            holdings=self._holdings,
            file_hash=self._file_hash,
            raw_text=self._text,
        )


@pytest.fixture
def ledger_factory(config):
    """A file-backed ledger + session factory so all nodes share one DB within a run."""
    engine = create_engine(config.db_url, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    return SessionLocal


@pytest.fixture
def statements(config):
    return {p.stem: p for p in generate_statements(config)}


def _orchestrator(config, ledger_factory, holdings, statement_path, file_hash="hash-abc"):
    fake = FakeIngestionAgent(str(statement_path), holdings, file_hash=file_hash)
    nodes = Nodes(config, ledger_factory, ingestion_agent=fake)
    compiled = build_graph(config, session_factory=ledger_factory,
                           checkpoint_path=":memory:", nodes=nodes)
    return Orchestrator(config, compiled=compiled), compiled


BROKERAGE_HOLDINGS = [
    _holding("VOO", "Vanguard S&P 500 ETF", AssetClass.EQUITY, Geography.US, 120, 60000, "USD"),
    _holding("AAPL", "Apple Inc.", AssetClass.EQUITY, Geography.US, 200, 44000, "USD"),
    _holding("BND", "Vanguard Total Bond ETF", AssetClass.DEBT, Geography.US, 150, 11000, "USD"),
]


def test_happy_path_reconciles_and_persists(config, ledger_factory, statements):
    """Sum (115000) matches the statement's stated total → ok → persisted, no interrupt."""
    orch, compiled = _orchestrator(config, ledger_factory, BROKERAGE_HOLDINGS,
                                   statements["fidelity_brokerage"])
    try:
        outcome = orch.ingest(str(statements["fidelity_brokerage"]), thread_id="t-happy")
    finally:
        compiled.close()

    assert outcome.status == "completed"
    assert outcome.reconcile_status == "ok"
    assert outcome.persisted_holdings == 3

    with ledger_factory() as s:
        assert s.scalar(select(func.count()).select_from(Holding)) == 3
        assert s.scalar(select(func.count()).select_from(Statement)) == 1


def test_mismatch_interrupts_then_resume_accept_persists(config, ledger_factory, statements):
    """Under-extraction (only 100000 vs stated 115000) → mismatch → interrupt; accept → persist."""
    short = [_holding("VOO", "Vanguard S&P 500 ETF", AssetClass.EQUITY, Geography.US, 120, 100000, "USD")]
    orch, compiled = _orchestrator(config, ledger_factory, short, statements["fidelity_brokerage"])
    try:
        outcome = orch.ingest(str(statements["fidelity_brokerage"]), thread_id="t-mismatch")
        assert outcome.status == "interrupted"
        assert "mismatch" in (outcome.question or "").lower() or outcome.question
        # Nothing persisted while paused.
        with ledger_factory() as s:
            assert s.scalar(select(func.count()).select_from(Holding)) == 0

        resumed = orch.resume("t-mismatch", "accept")
        assert resumed.status == "completed"
        assert resumed.persisted_holdings == 1
    finally:
        compiled.close()

    with ledger_factory() as s:
        assert s.scalar(select(func.count()).select_from(Holding)) == 1


def test_mismatch_resume_reject_persists_nothing(config, ledger_factory, statements):
    short = [_holding("VOO", "Vanguard S&P 500 ETF", AssetClass.EQUITY, Geography.US, 120, 100000, "USD")]
    orch, compiled = _orchestrator(config, ledger_factory, short, statements["fidelity_brokerage"])
    try:
        orch.ingest(str(statements["fidelity_brokerage"]), thread_id="t-reject")
        resumed = orch.resume("t-reject", "reject")
        assert resumed.status == "completed"
        assert resumed.persisted_holdings == 0
    finally:
        compiled.close()

    with ledger_factory() as s:
        assert s.scalar(select(func.count()).select_from(Holding)) == 0


def test_idempotent_reingest_skips(config, ledger_factory, statements):
    """Re-ingesting the same file_hash a second time persists nothing (idempotency §2a)."""
    # First run persists.
    orch1, c1 = _orchestrator(config, ledger_factory, BROKERAGE_HOLDINGS,
                              statements["fidelity_brokerage"], file_hash="dup-hash")
    try:
        orch1.ingest(str(statements["fidelity_brokerage"]), thread_id="t-first")
    finally:
        c1.close()

    # Second run, same hash, fresh thread → should detect already-ingested and skip.
    orch2, c2 = _orchestrator(config, ledger_factory, BROKERAGE_HOLDINGS,
                              statements["fidelity_brokerage"], file_hash="dup-hash")
    try:
        outcome = orch2.ingest(str(statements["fidelity_brokerage"]), thread_id="t-second")
    finally:
        c2.close()

    assert outcome.state.get("persisted_skipped") is True
    with ledger_factory() as s:
        assert s.scalar(select(func.count()).select_from(Holding)) == 3  # still just the first run


def test_reconcile_with_lost_text_escalates_instead_of_silently_persisting(config, ledger_factory):
    """Review #1: on a resume that lost the statement text, reconcile must NOT treat empty text as
    an automatic 'ok'. With holdings present but no text to check against, it escalates to the human
    (mismatch) rather than routing a possibly-wrong extraction straight to persist.
    """
    fake = FakeIngestionAgent.__new__(FakeIngestionAgent)  # skip PDF load; we drive reconcile directly
    nodes = Nodes(config, ledger_factory, ingestion_agent=fake)

    state = {
        "extracted": [{"market_value": "100000", "asset_class": "equity",
                       "geography": "us", "currency": "USD"}],
        "raw_text": "",          # text unavailable (e.g. cross-process resume before this fix)
        "file_hash": "hash-xyz",
    }
    out = nodes.reconcile(state)

    assert out["reconcile_status"] == "mismatch"
    assert out["stated_total"] is None


def test_checkpointer_persists_state_across_get_state(config, ledger_factory, statements):
    """The paused run's State is durable in the checkpointer (resumable after the process 'forgets')."""
    short = [_holding("VOO", "Vanguard S&P 500 ETF", AssetClass.EQUITY, Geography.US, 120, 100000, "USD")]
    orch, compiled = _orchestrator(config, ledger_factory, short, statements["fidelity_brokerage"])
    try:
        orch.ingest(str(statements["fidelity_brokerage"]), thread_id="t-durable")
        snap = compiled.graph.get_state({"configurable": {"thread_id": "t-durable"}})
        assert snap.next == ("ask_user",)                       # paused before ask_user
        assert snap.values.get("reconcile_status") == "mismatch"
    finally:
        compiled.close()
