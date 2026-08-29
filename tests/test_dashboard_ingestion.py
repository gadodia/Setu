"""Dashboard document ingestion: upload guardrails, status, and human review."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from setu.agents.orchestrator import RunOutcome
from setu.dashboard.server import create_app
from setu.models import Base


class ImmediateSubmitter:
    def submit(self, function, *args):
        function(*args)


class FakeOrchestrator:
    def __init__(self, outcome: RunOutcome, resumed: RunOutcome | None = None):
        self.outcome = outcome
        self.resumed = resumed or outcome

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def ingest(
        self,
        _path: str,
        _thread_id: str,
        source_name: str | None = None,
    ) -> RunOutcome:
        assert source_name is not None
        return self.outcome

    def resume(self, _thread_id: str, _decision: str) -> RunOutcome:
        return self.resumed


def _client(config, outcome: RunOutcome, resumed: RunOutcome | None = None):
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    orchestrator = FakeOrchestrator(outcome, resumed)
    app = create_app(
        config=config,
        session_factory=sessions,
        orchestrator_factory=lambda: orchestrator,
        ingestion_submitter=ImmediateSubmitter(),
    )
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"password": config.dashboard_password.get_secret_value()},
    )
    assert response.status_code == 200
    return client, sessions


def _token(client: TestClient) -> str:
    return client.get("/api/session").json()["request_token"]


def test_pdf_upload_runs_existing_ingestion_and_deletes_temporary_file(config):
    outcome = RunOutcome(
        status="completed",
        state={"document_kind": "POLICY"},
        persisted_policies=2,
        persisted_obligations=1,
        reconcile_status="ok",
    )
    client, _sessions = _client(config, outcome)

    response = client.post(
        "/api/ingestions",
        headers={"X-Setu-Request-Token": _token(client)},
        files={"file": ("synthetic-lic.pdf", b"%PDF-1.4\nsynthetic", "application/pdf")},
    )

    assert response.status_code == 202
    run = response.json()
    assert run["source_name"] == "synthetic-lic.pdf"
    assert run["status"] == "completed"
    assert run["document_kind"] == "POLICY"
    assert run["persisted_policies"] == 2
    assert list(config.paths.inbox_dir.iterdir()) == []


def test_duplicate_upload_is_reported_as_existing_record_not_zero_extraction(config):
    outcome = RunOutcome(
        status="completed",
        state={"document_kind": "POLICY", "already_ingested": True, "persisted_skipped": True},
        reconcile_status="ok",
    )
    client, _sessions = _client(config, outcome)

    run = client.post(
        "/api/ingestions",
        headers={"X-Setu-Request-Token": _token(client)},
        files={"file": ("existing.pdf", b"%PDF-1.4\nsynthetic", "application/pdf")},
    ).json()

    assert run["status"] == "completed"
    assert run["reconcile_status"] == "duplicate"


def test_upload_rejects_non_pdf_content_and_requires_request_token(config):
    client, _sessions = _client(config, RunOutcome(status="completed"))

    missing_token = client.post(
        "/api/ingestions",
        files={"file": ("document.pdf", b"%PDF-1.4\nsynthetic", "application/pdf")},
    )
    wrong_content = client.post(
        "/api/ingestions",
        headers={"X-Setu-Request-Token": _token(client)},
        files={"file": ("document.pdf", b"not a pdf", "application/pdf")},
    )

    assert missing_token.status_code == 403
    assert wrong_content.status_code == 415
    assert list(config.paths.inbox_dir.iterdir()) == []


def test_interrupted_run_appears_in_review_queue_and_can_be_rejected(config):
    paused = RunOutcome(
        status="interrupted",
        state={"document_kind": "HOLDINGS", "sum_extracted": "100", "stated_total": "120"},
        question="Extracted total differs from the stated total. Accept the extraction?",
        reconcile_status="mismatch",
    )
    resumed = RunOutcome(
        status="completed",
        state={"document_kind": "HOLDINGS"},
        persisted_holdings=0,
        reconcile_status="mismatch",
    )
    client, _sessions = _client(config, paused, resumed)
    token = _token(client)
    upload = client.post(
        "/api/ingestions",
        headers={"X-Setu-Request-Token": token},
        files={"file": ("statement.pdf", b"%PDF-1.4\nsynthetic", "application/pdf")},
    ).json()

    reviews = client.get("/api/ingestions?status=review").json()["runs"]
    decision = client.post(
        f"/api/ingestions/{upload['id']}/decision",
        headers={"X-Setu-Request-Token": token},
        json={"decision": "reject"},
    )

    assert len(reviews) == 1
    assert reviews[0]["question"].startswith("Extracted total differs")
    assert "raw_text" not in str(reviews).lower()
    assert decision.status_code == 202
    assert decision.json()["status"] == "rejected"


def test_upload_filename_is_reduced_to_a_safe_display_name(config):
    client, _sessions = _client(config, RunOutcome(status="completed"))

    response = client.post(
        "/api/ingestions",
        headers={"X-Setu-Request-Token": _token(client)},
        files={"file": ("../../private-policy.pdf", b"%PDF-1.4\nsynthetic", "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["source_name"] == "private-policy.pdf"
    assert not Path(response.json()["source_name"]).is_absolute()


def test_incomplete_policy_review_cannot_be_force_accepted(config):
    paused = RunOutcome(
        status="interrupted",
        state={"document_kind": "POLICY"},
        question=(
            "Policy review required: renewal notice is incomplete. "
            "This document cannot be persisted until it contains complete evidence. [reject]"
        ),
        reconcile_status="mismatch",
    )
    client, _sessions = _client(config, paused)
    token = _token(client)
    upload = client.post(
        "/api/ingestions",
        headers={"X-Setu-Request-Token": token},
        files={"file": ("renewal.pdf", b"%PDF-1.4\nsynthetic", "application/pdf")},
    ).json()

    response = client.post(
        f"/api/ingestions/{upload['id']}/decision",
        headers={"X-Setu-Request-Token": token},
        json={"decision": "accept"},
    )

    assert upload["allow_accept"] is False
    assert response.status_code == 409
