"""The LangGraph State — Setu's *working memory* for one ingestion run.

This TypedDict flows through every node; each node returns a partial dict that LangGraph merges in.
The SQLite checkpointer (build.py) snapshots this after every node, so the whole thing must be
JSON/msgpack-serializable — hence **money is carried as decimal strings, not Decimal objects**, and
dates as ISO strings. Nodes convert to Decimal at the point of computation and back to str before
returning.

Field lifecycle over a run:
  goal, statement_path        set at invoke
  extracted, currency, raw_text   written by `ingest`
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
    cost_basis: str | None    # source-stated total acquisition cost; null when absent
    currency: str


class ExtractedPolicyDict(TypedDict, total=False):
    policy_name: str
    policy_type: str
    policy_number: str | None
    plan_number: str | None
    status: str | None
    sum_assured: str | None
    surrender_value: str | None
    fund_value: str | None
    maturity_value: str | None
    premium_amount: str | None
    premium_due_date: str | None
    commencement_date: str | None
    maturity_date: str | None
    policy_term_years: int | None
    premium_payment_term_years: int | None
    premium_mode: str | None
    vested_bonus: str | None
    guaranteed_additions: str | None
    maturity_benefit_4pct: str | None
    maturity_benefit_8pct: str | None
    units: str | None
    nav: str | None
    currency: str
    asset_value: str | None
    valuation_basis: str


class ExtractedBalanceDict(TypedDict, total=False):
    amount: str
    currency: str
    source_label: str
    verification_amount: str | None


class TraceEvent(TypedDict, total=False):
    kind: Literal["thought", "action", "observation", "ask_user"]
    node: str
    content: str


ReconcileStatus = Literal["pending", "ok", "mismatch", "abandoned"]


class SetuState(TypedDict, total=False):
    # --- inputs (set at invoke) ---
    goal: str
    statement_path: str
    source_name: str

    # --- written by `ingest` ---
    institution: str
    account_ref: str | None
    period_end: str                       # ISO date parsed from the statement
    currency: str
    document_kind: Literal["HOLDINGS", "POLICY", "BANK"]
    policy_document_type: Literal[
        "POLICY_STATEMENT", "PREMIUM_NOTICE", "PREMIUM_RECEIPT", "UNKNOWN"
    ]
    extracted: list[ExtractedHoldingDict]
    extracted_policies: list[ExtractedPolicyDict]
    extracted_balance: ExtractedBalanceDict | None
    file_hash: str
    already_ingested: bool
    raw_text: str                         # statement text reconcile checks the stated total against;
                                          # carried in State (not a Nodes-instance cache) so it
                                          # survives cross-process / crash-recovery resume

    # --- written by `reconcile` ---
    stated_total: str | None              # decimal string parsed from the statement's Total line
    sum_extracted: str                    # decimal string
    reconcile_status: ReconcileStatus
    reconcile_delta: str                  # |stated - summed| as a decimal string (0 if no stated total)
    policy_review_reason: str | None
    policy_warnings: list[str]

    # --- human-in-the-loop ---
    pending_question: str | None          # populated right before the ask_user interrupt
    user_decision: str | None             # "accept" / "reject" — supplied on resume

    # --- written by `persist` ---
    persisted_holdings: int
    persisted_balances: int
    persisted_policies: int
    persisted_obligations: int
    persisted_skipped: bool               # true when the statement was already in the ledger

    # --- control ---
    retries: int
    trace: Annotated[list[TraceEvent], _append]
    error: str | None


def new_state(goal: str, statement_path: str, source_name: str | None = None) -> SetuState:
    """Build a fresh State for a run (keeps invoke sites from forgetting required fields)."""
    return SetuState(
        goal=goal,
        statement_path=statement_path,
        source_name=source_name or statement_path.rsplit("/", 1)[-1],
        extracted=[],
        extracted_policies=[],
        extracted_balance=None,
        retries=0,
        trace=[],
    )
