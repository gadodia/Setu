"""Assemble and compile the Setu ingestion graph.

The graph is the *runtime* for the ReAct ingestion loop:

    START → ingest → reconcile ─┬─(ok)────────────→ persist → END
                                ├─(mismatch)──────→ ask_user → persist → END
                                └─(retry, bounded)→ reconcile

The **conditional edge after `reconcile`** is the self-correcting branch (concept #4 as control
flow). Compilation attaches a **SQLite checkpointer** — it snapshots State after every node, keyed by
thread_id (durability, resumability, conversation continuity, audit). This DB is *separate* from the
ledger DB. Human-in-the-loop is driven by a **dynamic `interrupt()`** inside the `ask_user` node:
it pauses+persists the run and returns a question payload under `__interrupt__`, then
`invoke(Command(resume=...))` continues with State intact.

`build_graph()` returns the compiled graph plus the checkpointer connection (the caller keeps it
open for the graph's lifetime; SqliteSaver needs a live connection).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from setu.config import Config, load_config
from setu.db import get_session
from setu.graph.nodes import Nodes
from setu.graph.state import SetuState

MAX_RETRIES = 1  # reconcile→retry→reconcile at most this many times before escalating to the human


def route_after_reconcile(state: SetuState) -> str:
    """Conditional edge: turn the reconciliation verdict into the next node.

    ok        → persist         (reconciled, or no stated total to disconfirm)
    mismatch  → retry once (re-run reconcile), then escalate to ask_user
    """
    status = state.get("reconcile_status", "ok")
    if status == "ok":
        return "ok"
    if state.get("retries", 0) < MAX_RETRIES:
        return "retry"
    return "mismatch"


def _bump_retries(state: SetuState) -> dict:
    """A no-op-ish node on the retry path that increments the bound counter and logs a re-plan."""
    from setu.graph.state import TraceEvent

    n = state.get("retries", 0) + 1
    return {
        "retries": n,
        "trace": [TraceEvent(kind="thought", node="replan",
                             content=f"Reconciliation mismatch — re-planning (attempt {n}).")],
    }


@dataclass
class CompiledGraph:
    graph: Any                       # the compiled LangGraph
    checkpointer: Any                # SqliteSaver (keep referenced so its conn stays open)
    _conn: sqlite3.Connection

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


def build_graph(
    config: Config | None = None,
    session_factory: Callable[[], Any] | None = None,
    checkpoint_path: str | Path | None = None,
    nodes: Nodes | None = None,
) -> CompiledGraph:
    """Build + compile the ingestion graph with a SQLite checkpointer.

    `checkpoint_path` defaults to `data/checkpoints.db` (NOT the ledger `setu.db`). Pass
    `:memory:` in tests. `nodes` can be injected for tests (fake local model / in-memory ledger).
    """
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph

    config = config or load_config()
    session_factory = session_factory or (lambda: get_session(config))
    nodes = nodes or Nodes(config, session_factory)

    if checkpoint_path is None:
        checkpoint_path = config.paths.data_dir / "checkpoints.db"
    conn = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    g = StateGraph(SetuState)
    g.add_node("ingest", nodes.ingest)
    g.add_node("reconcile", nodes.reconcile)
    g.add_node("replan", _bump_retries)
    g.add_node("ask_user", nodes.ask_user)
    g.add_node("persist", nodes.persist)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "reconcile")
    g.add_conditional_edges(
        "reconcile",
        route_after_reconcile,
        {"ok": "persist", "mismatch": "ask_user", "retry": "replan"},
    )
    g.add_edge("replan", "reconcile")   # bounded self-correction loop
    g.add_edge("ask_user", "persist")
    g.add_edge("persist", END)

    # Human-in-the-loop is driven by the *dynamic* `interrupt()` call inside the ask_user node
    # (not a static interrupt_before): it pauses+persists the run and carries a question payload
    # that `invoke` returns under `__interrupt__`; `Command(resume=...)` continues it.
    compiled = g.compile(checkpointer=checkpointer)
    return CompiledGraph(graph=compiled, checkpointer=checkpointer, _conn=conn)
