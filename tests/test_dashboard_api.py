"""Local dashboard API: real ledger data, agent registry, and privacy boundary."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from setu.dashboard.server import create_app
from setu.models import Base, PolicyType, PolicyValue, Statement
from setu.synthetic.generate import seed_portfolio


def _client(
    config,
    *,
    include_unverified_legacy_policy: bool = False,
    question_runner=None,
):
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with sessions() as session:
        seed_portfolio(session, config)
        statement = Statement(
            institution="Synthetic LIC",
            account_ref="****4821",
            file_name="lic-policy.pdf",
            file_hash="dashboard-statement-hash",
            period_end=date(2026, 7, 31),
        )
        session.add(statement)
        session.flush()
        if include_unverified_legacy_policy:
            insurance_value = session.scalar(select(PolicyValue).limit(1))
            session.add(PolicyValue(
                account_id=insurance_value.account_id,
                statement_id=statement.id,
                policy_name="TERM",
                policy_type=PolicyType.TERM,
                sum_assured=Decimal("300000"),
                asset_value=Decimal("0"),
                currency="INR",
                as_of_date=date(2026, 7, 31),
            ))
        session.commit()
    client = TestClient(create_app(
        config=config,
        session_factory=sessions,
        question_runner=question_runner,
    ))
    response = client.post(
        "/api/auth/login",
        json={"password": config.dashboard_password.get_secret_value()},
    )
    assert response.status_code == 200
    return client


def test_overview_is_backed_by_real_ledger(config):
    client = _client(config)

    response = client.get("/api/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["base_currency"] == "USD"
    assert float(body["net_worth"]) > 0
    assert body["counts"]["accounts"] == 6
    assert body["counts"]["policies"] == 3
    assert body["counts"]["obligations"] == 3
    assert any(position["kind"] == "insurance" for position in body["positions"])
    assert "EQUITY" in body["allocation"]["asset_class"]
    assert body["performance"]["status"] == "available"
    assert Decimal(body["performance"]["unrealized_gain"]) == Decimal("79090.200000000")
    assert any(
        insight["title"] == "USD exposure exceeds your guardrail"
        for insight in body["insights"]
    )
    voo = next(position for position in body["positions"] if position["label"] == "Vanguard S&P 500 ETF")
    assert voo["base_cost_basis"] == "48000.0000"
    assert Decimal(voo["roi_fraction"]) == Decimal("0.25")
    assert body["health"]["label"] == "Needs attention"
    assert body["health"]["horizons"]["short_term"]["status"] == "elevated"
    assert body["health"]["horizons"]["long_term"]["status"] == "elevated"
    assert len(body["health"]["actions"]) == 5


def test_agent_registry_supports_future_workspaces(config):
    client = _client(config)

    body = client.get("/api/agents").json()

    assert [agent["id"] for agent in body["agents"]] == ["financial", "forms", "research"]
    assert body["agents"][0]["status"] == "active"
    assert body["agents"][1]["status"] == "planned"


def test_activity_exposes_provenance_not_hidden_reasoning(config):
    client = _client(config)

    body = client.get("/api/activity").json()

    assert body["events"][0]["kind"] == "document_ingested"
    assert body["events"][0]["source"] == "lic-policy.pdf"
    assert "thought" not in str(body).lower()
    assert "raw_text" not in str(body).lower()


def test_dashboard_rejects_untrusted_hosts(config):
    client = _client(config)

    response = client.get("/api/overview", headers={"host": "public.example.com"})

    assert response.status_code == 400


def test_policy_details_expose_coverage_value_source_and_quality(config):
    client = _client(config)

    response = client.get("/api/policies")

    assert response.status_code == 200
    policies = response.json()["policies"]
    assert len(policies) == 3
    term = next(policy for policy in policies if policy["policy_type"] == "TERM")
    assert term["sum_assured"] == "10000000.0000"
    assert term["asset_value"] == "0.0000"
    assert term["valuation_basis"] == "protection_only"
    assert term["quality_status"] == "verified"
    assert "account_ref" not in str(policies)
    lic = next(policy for policy in policies if policy["policy_type"] == "ENDOWMENT")
    assert lic["asset_value"] is None
    assert lic["valuation_basis"] == "current_value_not_provided"
    assert lic["quality_status"] == "partial"


def test_unverified_legacy_policy_does_not_present_zero_as_a_known_value(config):
    client = _client(config, include_unverified_legacy_policy=True)

    policies = client.get("/api/policies").json()["policies"]
    policy = next(item for item in policies if item["extracted_policy_name"] == "TERM")

    assert policy["asset_value"] is None
    assert policy["valuation_basis"] == "unverified_legacy_value"
    assert policy["quality_status"] == "needs_review"
    assert policy["projection"]["status"] == "insufficient_evidence"


def test_ask_endpoint_masks_identifiers_and_returns_only_sanitized_result(config):
    received = []

    def answer(question, _session, _config):
        received.append(question)
        return {
            "answer": "USD exposure is above the configured guardrail.",
            "tools_used": ["analyze_portfolio"],
            "rounds": 2,
            "privacy": "Only sanitized ledger calculations were sent to Claude.",
        }

    client = _client(config, question_runner=answer)
    token = client.get("/api/session").json()["request_token"]

    forbidden = client.post("/api/ask", json={"question": "Analyze policy ABCD123456789"})
    assert forbidden.status_code == 403

    response = client.post(
        "/api/ask",
        headers={"X-Setu-Request-Token": token},
        json={"question": "Analyze policy ABCD123456789 as of 2026-08-28"},
    )

    assert response.status_code == 200
    assert received == ["Analyze policy ****6789 as of 2026-08-28"]
    assert response.json()["tools_used"] == ["analyze_portfolio"]
    assert "raw_text" not in str(response.json())


def test_ask_endpoint_returns_safe_rendered_markdown_and_explicit_limits(config):
    def answer(_question, _session, _config):
        return {
            "answer": (
                "### Answer\n\n"
                "Your portfolio has a measurable return.\n\n"
                "### Key evidence\n\n"
                "- **ROI:** source-backed\n"
                "- <script>alert('unsafe')</script> is not executable"
            ),
            "tools_used": ["analyze_portfolio"],
            "rounds": 2,
            "truncated": True,
            "privacy": "Only sanitized ledger calculations were sent to Claude.",
        }

    client = _client(config, question_runner=answer)
    token = client.get("/api/session").json()["request_token"]
    response = client.post(
        "/api/ask",
        headers={"X-Setu-Request-Token": token},
        json={"question": "Explain my portfolio return"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer_format"] == "commonmark"
    assert "<h3>Answer</h3>" in body["answer_html"]
    assert "<ul>" in body["answer_html"]
    assert "<strong>ROI:</strong>" in body["answer_html"]
    assert "<script>" not in body["answer_html"]
    assert "&lt;script&gt;" in body["answer_html"]
    assert body["truncated"] is True
    assert body["limits"] == {
        "max_output_tokens": config.claude.max_output_tokens,
        "max_tool_rounds": config.claude.max_tool_rounds,
        "target_answer_words": config.claude.target_answer_words,
    }
