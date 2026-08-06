"""The LangGraph State — Setu's *working memory* for one ingestion run.

This TypedDict flows through every node; each node returns a partial dict that LangGraph merges in.
The SQLite checkpointer (build.py) snapshots this after every node, so the whole thing must be
JSON/msgpack-serializable — hence **money is carried as decimal strings, not Decimal objects**, and
dates as ISO strings. Nodes convert to Decimal at the point of computation and back to str before
returning.

Field lifecycle over a run:
  goal, statement_path        set at invoke
  extracted, currency         written by `ingest`
  stated_total, sum_extracted,
  reconcile_status, reconcile_delta   written by `reconcile`
  user_decision               written on resume after the `ask_user` interrupt
  persisted_*                 written by `persist`
  retries                     bumped by the retry branch (bounds the self-correction loop)
  trace                       appended by every node (the visible Thought/Action/Observation log)
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict


def _append(existing: list | None, new: list | None) -> list:
    """Reducer: concatenate trace lists across node updates instead of overwriting."""
    return (existing or []) + (new or [])


class ExtractedHoldingDict(TypedDict, total=False):
    symbol: str | None
    name: str
    asset_class: str          # AssetClass.value
    geography: str            # Geography.value
    quantity: str             # decimal string
    market_value: str         # decimal string
    currency: str


class TraceEvent(TypedDict, total=False):
    kind: Literal["thought", "action", "observation", "ask_user"]
    node: str
    content: str


ReconcileStatus = Literal["pending", "ok", "mismatch", "abandoned"]


class SetuState(TypedDict, total=False):
    # --- inputs (set at invoke) ---
    goal: str
    statement_path: str

    # --- written by `ingest` ---
    institution: str
    account_ref: str | None
    period_end: str                       # ISO date parsed from the statement
    currency: str
    extracted: list[ExtractedHoldingDict]
    file_hash: str
    already_ingested: bool

    # --- written by `reconcile` ---
    stated_total: str | None              # decimal string parsed from the statement's Total line
    sum_extracted: str                    # decimal string
    reconcile_status: ReconcileStatus
    reconcile_delta: str                  # |stated - summed| as a decimal string (0 if no stated total)

    # --- human-in-the-loop ---
    pending_question: str | None          # populated right before the ask_user interrupt
    user_decision: str | None             # "accept" / "reject" — supplied on resume

    # --- written by `persist` ---
    persisted_holdings: int
    persisted_skipped: bool               # true when the statement was already in the ledger

    # --- control ---
    retries: int
    trace: Annotated[list[TraceEvent], _append]
    error: str | None


def new_state(goal: str, statement_path: str) -> SetuState:
    """Build a fresh State for a run (keeps invoke sites from forgetting required fields)."""
    return SetuState(
        goal=goal,
        statement_path=statement_path,
        extracted=[],
        retries=0,
        trace=[],
    )
