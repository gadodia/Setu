"""Node functions — each wraps an agent/tool, takes State, returns a partial State update.

The nodes are deliberately thin: they translate between the serializable State (decimal strings,
ISO dates) and the agents/tools (Decimal, date), append trace events, and set the control fields the
edges route on. All financial computation lives in the agents/tools, never here and never in an LLM.

Nodes are constructed with their dependencies (config, local client, a Session factory) by
`build.py` via `make_nodes`, so they stay unit-testable with an in-memory DB and a fake model.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from setu.agents.ingestion_agent import IngestionAgent, IngestionResult
from setu.agents.reconciliation_agent import ReconciliationAgent
from setu.config import Config
from setu.db import statement_already_ingested
from setu.extraction import ExtractedHolding
from setu.graph.state import SetuState, TraceEvent
from setu.models import (
    Account,
    AccountType,
    AssetClass,
    Geography,
    Holding,
    Institution,
    Statement,
)

SessionFactory = Callable[[], Session]


def _ev(kind: str, node: str, content: str) -> TraceEvent:
    return TraceEvent(kind=kind, node=node, content=content)


def _holding_dicts(holdings: list[ExtractedHolding]) -> list[dict]:
    return [
        {
            "symbol": h.symbol,
            "name": h.name,
            "asset_class": h.asset_class.value,
            "geography": h.geography.value,
            "quantity": h.as_decimal("quantity").__str__(),
            "market_value": h.as_decimal("market_value").__str__(),
            "currency": h.currency.upper(),
        }
        for h in holdings
    ]


class Nodes:
    """Bundle of node callables sharing config, an IngestionAgent, and a Session factory."""

    def __init__(
        self,
        config: Config,
        session_factory: SessionFactory,
        ingestion_agent: IngestionAgent | None = None,
        reconciliation_agent: ReconciliationAgent | None = None,
    ):
        self.config = config
        self.session_factory = session_factory
        self.ingestion = ingestion_agent or IngestionAgent(config)
        self.reconciliation = reconciliation_agent or ReconciliationAgent(config)
        # Ingestion produces the raw text reconcile needs; cache it per file_hash within a run.
        self._raw_text: dict[str, str] = {}

    # --- ingest -----------------------------------------------------------------------------
    def ingest(self, state: SetuState) -> dict:
        path = state["statement_path"]
        trace = [_ev("thought", "ingest", f"Parsing and extracting holdings from {path}.")]

        res: IngestionResult = self.ingestion.run(path)
        self._raw_text[res.file_hash] = res.raw_text

        # Idempotency check (§2a): already in the ledger? Short-circuit downstream persistence.
        with self.session_factory() as session:
            already = statement_already_ingested(session, res.file_hash)

        trace.append(_ev(
            "observation", "ingest",
            f"{res.institution}: extracted {len(res.holdings)} holding(s) in {res.currency}"
            + (" (already ingested)" if already else "."),
        ))
        return {
            "institution": res.institution,
            "account_ref": res.account_ref,
            "period_end": res.period_end.isoformat(),
            "currency": res.currency,
            "extracted": _holding_dicts(res.holdings),
            "file_hash": res.file_hash,
            "already_ingested": already,
            "trace": trace,
        }

    # --- reconcile --------------------------------------------------------------------------
    def reconcile(self, state: SetuState) -> dict:
        extracted = state.get("extracted", [])
        summed = sum((Decimal(h["market_value"]) for h in extracted), Decimal("0"))
        text = self._raw_text.get(state.get("file_hash", ""), "")

        res = self.reconciliation.run(text, summed)

        stated = "none" if res.stated_total is None else f"{res.stated_total}"
        trace = [
            _ev("thought", "reconcile",
                f"Summed extracted value = {summed}; checking against the statement's stated total."),
            _ev("observation", "reconcile",
                f"stated={stated}, summed={summed}, delta={res.delta} → {res.status} "
                f"(tolerance {self.reconciliation.tolerance})."),
        ]
        return {
            "stated_total": None if res.stated_total is None else str(res.stated_total),
            "sum_extracted": str(summed),
            "reconcile_delta": str(res.delta),
            "reconcile_status": res.status,
            "trace": trace,
        }

    # --- ask_user (human-in-the-loop; interrupt happens here) -------------------------------
    def ask_user(self, state: SetuState) -> dict:
        # Import here so the module imports cleanly even if langgraph isn't installed (tests of
        # agents/tools in isolation don't need it).
        from langgraph.types import interrupt

        question = (
            f"Reconciliation mismatch for {state.get('institution', 'this statement')}: "
            f"extracted total {state.get('sum_extracted')} vs stated {state.get('stated_total')} "
            f"(delta {state.get('reconcile_delta')}). Accept the extraction anyway? [accept/reject]"
        )
        # interrupt() pauses+persists the run and returns the resume value on continuation.
        decision = interrupt({"question": question, "state_summary": {
            "institution": state.get("institution"),
            "sum_extracted": state.get("sum_extracted"),
            "stated_total": state.get("stated_total"),
        }})
        decision = str(decision).strip().lower()
        return {
            "pending_question": question,
            "user_decision": decision,
            "trace": [_ev("ask_user", "ask_user", f"Human decision: {decision}")],
        }

    # --- persist ----------------------------------------------------------------------------
    def persist(self, state: SetuState) -> dict:
        # A rejected mismatch persists nothing.
        if state.get("user_decision") == "reject":
            return {
                "persisted_holdings": 0,
                "persisted_skipped": False,
                "trace": [_ev("observation", "persist", "User rejected — nothing written to ledger.")],
            }

        if state.get("already_ingested"):
            return {
                "persisted_holdings": 0,
                "persisted_skipped": True,
                "trace": [_ev("observation", "persist",
                              "Statement already in ledger (idempotent skip).")],
            }

        from datetime import date

        extracted = state.get("extracted", [])
        period_end = date.fromisoformat(state["period_end"])
        n = 0
        with self.session_factory() as session:
            stmt = Statement(
                institution=state.get("institution", "Unknown"),
                account_ref=state.get("account_ref"),
                file_name=state.get("statement_path", "").split("/")[-1],
                file_hash=state["file_hash"],
                period_end=period_end,
            )
            session.add(stmt)

            inst = Institution(
                name=state.get("institution", "Unknown"),
                geography=_geo_of(extracted),
            )
            account = Account(
                institution=inst,
                name=state.get("institution", "Unknown"),
                account_type=AccountType.BROKERAGE,   # refined by classification in a later week
                currency=state.get("currency", "USD"),
                account_ref=state.get("account_ref"),
            )
            session.add(account)
            session.flush()  # assign stmt.id / account.id

            for h in extracted:
                session.add(Holding(
                    account_id=account.id,
                    statement_id=stmt.id,
                    symbol=h.get("symbol"),
                    name=h.get("name", ""),
                    asset_class=AssetClass(h["asset_class"]),
                    geography=Geography(h["geography"]),
                    quantity=Decimal(h.get("quantity", "0")),
                    market_value=Decimal(h["market_value"]),
                    currency=h.get("currency", "USD"),
                    as_of_date=period_end,
                ))
                n += 1
            session.commit()

        return {
            "persisted_holdings": n,
            "persisted_skipped": False,
            "trace": [_ev("action", "persist", f"Wrote {n} holding(s) + statement to the ledger.")],
        }


def _geo_of(extracted: list[dict]) -> Geography:
    """Account geography = the geography of its holdings (India if any INR/INDIA present)."""
    for h in extracted:
        if h.get("geography") == Geography.INDIA.value:
            return Geography.INDIA
    return Geography.US
