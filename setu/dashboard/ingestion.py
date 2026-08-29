"""Durable, privacy-safe coordination for dashboard PDF ingestion."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from setu.agents.orchestrator import Orchestrator, RunOutcome
from setu.config import Config
from setu.models import IngestionRun
from setu.tools.pdf_extract import OcrError


class Submitter(Protocol):
    def submit(self, function: Callable[..., Any], *args: Any) -> Any: ...


OrchestratorFactory = Callable[[], Orchestrator]
SessionFactory = Callable[[], Session]


class IngestionCoordinator:
    """Run one local ingestion at a time and retain only sanitized workflow metadata."""

    def __init__(
        self,
        config: Config,
        sessions: SessionFactory,
        orchestrator_factory: OrchestratorFactory | None = None,
        submitter: Submitter | None = None,
    ):
        self.config = config
        self.sessions = sessions
        self.orchestrator_factory = orchestrator_factory or (lambda: Orchestrator(config))
        self.submitter = submitter or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="setu-ingestion",
        )
        self._recover_interrupted_processes()

    def start(self, path: Path, source_name: str) -> dict[str, Any]:
        run_id = uuid4().hex
        with self.sessions() as session:
            session.add(IngestionRun(
                id=run_id,
                thread_id=f"ui-{run_id}",
                source_name=source_name,
                status="queued",
            ))
            session.commit()
        self.submitter.submit(self._ingest, run_id, path)
        return self.get(run_id)

    def resume(self, run_id: str, decision: str) -> dict[str, Any]:
        with self.sessions() as session:
            run = session.get(IngestionRun, run_id)
            if run is None:
                raise LookupError("Unknown ingestion run.")
            if run.status != "review":
                raise ValueError("This ingestion run is not waiting for review.")
            if decision == "accept" and not _allow_accept(run):
                raise ValueError(
                    "This policy evidence is incomplete and cannot be accepted. "
                    "Reject it and upload a complete policy statement."
                )
            run.status = "processing"
            run.error = None
            session.commit()
        self.submitter.submit(self._resume, run_id, decision)
        return self.get(run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            run = session.get(IngestionRun, run_id)
            if run is None:
                raise LookupError("Unknown ingestion run.")
            return _serialize(run)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.sessions() as session:
            query = select(IngestionRun).order_by(
                IngestionRun.created_at.desc(),
                IngestionRun.id.desc(),
            ).limit(50)
            if status:
                query = query.where(IngestionRun.status == status)
            return [_serialize(run) for run in session.scalars(query).all()]

    def _ingest(self, run_id: str, path: Path) -> None:
        self._set_status(run_id, "processing")
        try:
            with self.sessions() as session:
                run = session.get(IngestionRun, run_id)
                if run is None:
                    return
                source_name = run.source_name
            with self.orchestrator_factory() as orchestrator:
                outcome = orchestrator.ingest(
                    str(path),
                    f"ui-{run_id}",
                    source_name=source_name,
                )
            self._record_outcome(run_id, outcome)
        except OcrError:
            self._fail(run_id, "OCR could not read this PDF. Check the local OCR installation and try again.")
        except Exception:
            self._fail(run_id, "Setu could not process this PDF. Check the local model and document format.")
        finally:
            path.unlink(missing_ok=True)

    def _resume(self, run_id: str, decision: str) -> None:
        try:
            with self.sessions() as session:
                run = session.get(IngestionRun, run_id)
                if run is None:
                    return
                thread_id = run.thread_id
            with self.orchestrator_factory() as orchestrator:
                outcome = orchestrator.resume(thread_id, decision)
            self._record_outcome(run_id, outcome, rejected=decision == "reject")
        except Exception:
            self._fail(run_id, "Setu could not apply this review decision. Please try again.")

    def _record_outcome(
        self,
        run_id: str,
        outcome: RunOutcome,
        *,
        rejected: bool = False,
    ) -> None:
        with self.sessions() as session:
            run = session.get(IngestionRun, run_id)
            if run is None:
                return
            run.document_kind = outcome.state.get("document_kind")
            run.reconcile_status = (
                "duplicate"
                if outcome.state.get("persisted_skipped") or outcome.state.get("already_ingested")
                else outcome.reconcile_status
            )
            run.persisted_holdings = outcome.persisted_holdings
            run.persisted_balances = outcome.persisted_balances
            run.persisted_policies = outcome.persisted_policies
            run.persisted_obligations = outcome.persisted_obligations
            run.question = outcome.question if outcome.status == "interrupted" else None
            run.status = (
                "review"
                if outcome.status == "interrupted"
                else "rejected"
                if rejected
                else "completed"
            )
            session.commit()

    def _set_status(self, run_id: str, status: str) -> None:
        with self.sessions() as session:
            run = session.get(IngestionRun, run_id)
            if run is not None:
                run.status = status
                session.commit()

    def _fail(self, run_id: str, message: str) -> None:
        with self.sessions() as session:
            run = session.get(IngestionRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = message
                session.commit()

    def close(self) -> None:
        if isinstance(self.submitter, Executor):
            self.submitter.shutdown(wait=False, cancel_futures=False)

    def _recover_interrupted_processes(self) -> None:
        """Fail stale workers after a dashboard restart and remove only Setu UI temp files."""
        with self.sessions() as session:
            stale = session.scalars(
                select(IngestionRun).where(IngestionRun.status.in_(("queued", "processing")))
            ).all()
            for run in stale:
                run.status = "failed"
                run.error = "Setu stopped before this import finished. Please upload the PDF again."
            if stale:
                session.commit()
        for path in self.config.paths.inbox_dir.glob(".ui-upload-*.pdf"):
            path.unlink(missing_ok=True)


def _serialize(run: IngestionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "source_name": run.source_name,
        "status": run.status,
        "document_kind": run.document_kind,
        "reconcile_status": run.reconcile_status,
        "question": run.question,
        "error": run.error,
        "persisted_holdings": run.persisted_holdings,
        "persisted_balances": run.persisted_balances,
        "persisted_policies": run.persisted_policies,
        "persisted_obligations": run.persisted_obligations,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "allow_accept": _allow_accept(run),
    }


def _allow_accept(run: IngestionRun) -> bool:
    return not (
        run.document_kind == "POLICY"
        and run.question is not None
        and "cannot be persisted" in run.question.lower()
    )
