"""Orchestrator — the ReAct planner that drives the ingestion graph.

At the coordination level this *is* the ReAct loop: it receives a goal ("ingest this statement"),
invokes the compiled LangGraph (whose nodes dispatch the specialized sub-agents), observes the
result, and — when reconciliation can't be resolved automatically — pauses for the human instead of
crashing. LangGraph's checkpointer makes that pause durable and resumable.

Public surface:
  Orchestrator.ingest(path, thread_id)  → RunOutcome (may be `interrupted`)
  Orchestrator.resume(thread_id, decision) → RunOutcome
The CLI renders RunOutcome.trace as Thought/Action/Observation and, on interrupt, prompts the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from setu.config import Config, load_config
from setu.graph.build import CompiledGraph, build_graph
from setu.graph.state import SetuState, TraceEvent, new_state


@dataclass
class RunOutcome:
    status: str                       # "completed" | "interrupted"
    state: dict = field(default_factory=dict)
    trace: list[TraceEvent] = field(default_factory=list)
    question: str | None = None       # populated when status == "interrupted"
    persisted_holdings: int = 0
    reconcile_status: str | None = None


class Orchestrator:
    def __init__(
        self,
        config: Config | None = None,
        compiled: CompiledGraph | None = None,
        checkpoint_path: str | Path | None = None,
    ):
        self.config = config or load_config()
        self._own = compiled is None
        self.compiled = compiled or build_graph(self.config, checkpoint_path=checkpoint_path)

    # --- lifecycle -----------------------------------------------------------------------
    def close(self) -> None:
        if self._own:
            self.compiled.close()

    def __enter__(self) -> "Orchestrator":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- goals ---------------------------------------------------------------------------
    def ingest(self, path: str, thread_id: str) -> RunOutcome:
        """Run the ingestion graph for one statement under a thread_id (its checkpoint key)."""
        cfg = {"configurable": {"thread_id": thread_id}}
        result = self.compiled.graph.invoke(new_state("ingest", path), cfg)
        return self._outcome(result, cfg)

    def resume(self, thread_id: str, decision: str) -> RunOutcome:
        """Continue a run that paused at ask_user, supplying the human's decision."""
        from langgraph.types import Command

        cfg = {"configurable": {"thread_id": thread_id}}
        result = self.compiled.graph.invoke(Command(resume=decision), cfg)
        return self._outcome(result, cfg)

    # --- result shaping ------------------------------------------------------------------
    def _outcome(self, result: dict, cfg: dict) -> RunOutcome:
        trace = result.get("trace", [])
        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            return RunOutcome(
                status="interrupted",
                state=self._clean(result),
                trace=trace,
                question=payload.get("question") if isinstance(payload, dict) else str(payload),
                reconcile_status=result.get("reconcile_status"),
            )
        return RunOutcome(
            status="completed",
            state=self._clean(result),
            trace=trace,
            persisted_holdings=result.get("persisted_holdings", 0),
            reconcile_status=result.get("reconcile_status"),
        )

    @staticmethod
    def _clean(result: dict) -> dict:
        return {k: v for k, v in result.items() if k not in ("__interrupt__", "trace")}
