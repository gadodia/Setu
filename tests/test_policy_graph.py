"""Graph behavior for insurance-policy valuation and persistence."""

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from setu.agents.ingestion_agent import IngestionResult
from setu.extraction import ExtractedPolicy
from setu.graph.nodes import Nodes
from setu.models import (
    Account,
    AccountType,
    Base,
    InsurancePolicy,
    Obligation,
    PolicyType,
    PolicyValue,
    Statement,
)


def _ledger_factory(config):
    engine = create_engine(config.db_url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def _base_state(**updates):
    state = {
        "statement_path": "/synthetic/lic-policy.pdf",
        "institution": "Life Insurance Corporation of India",
        "account_ref": "POLICY-1234",
        "period_end": "2026-06-30",
        "currency": "INR",
        "file_hash": "policy-hash-1",
        "document_kind": "POLICY",
        "extracted": [],
        "raw_text": "Synthetic policy statement",
        "already_ingested": False,
    }
    state.update(updates)
    return state


def test_policy_ingest_does_not_checkpoint_raw_document_text(config):
    sessions = _ledger_factory(config)

    class FakePolicyIngestion:
        def run(self, path):
            return IngestionResult(
                institution="Life Insurance Corporation of India",
                account_ref="****1234",
                period_end=date(2026, 6, 30),
                currency="INR",
                holdings=[],
                file_hash="private-policy-hash",
                raw_text="PRIVATE POLICY TEXT WITH PERSONAL DETAILS",
                document_kind="POLICY",
                policies=[ExtractedPolicy(
                    policy_name="LIC New Tech-Term",
                    policy_type=PolicyType.TERM,
                    sum_assured="10000000",
                    currency="INR",
                )],
            )

    out = Nodes(config, sessions, ingestion_agent=FakePolicyIngestion()).ingest(
        {"statement_path": "/private/lic.pdf"}
    )

    assert out["raw_text"] == ""
    assert "PRIVATE POLICY TEXT" not in str(out)
    assert out["extracted_policies"][0]["sum_assured"] == "10000000"


def test_policy_reconcile_and_persist_writes_values_and_premium_obligations(config):
    sessions = _ledger_factory(config)
    nodes = Nodes(config, sessions)
    policies = [
        {
            "policy_name": "LIC New Tech-Term",
            "policy_type": PolicyType.TERM.value,
            "sum_assured": "10000000",
            "premium_amount": "25000",
            "premium_due_date": "15-Sep-2026",
            "currency": "INR",
        },
        {
            "policy_name": "Tata AIA Fortune Pro",
            "policy_type": PolicyType.ULIP.value,
            "fund_value": "603703.26",
            "premium_amount": "50000",
            "premium_due_date": "01/10/2026",
            "currency": "INR",
        },
    ]
    state = _base_state(extracted_policies=policies, source_name="original-policy.pdf")

    reconciled = nodes.reconcile(state)
    assert reconciled["reconcile_status"] == "ok"
    assert reconciled["sum_extracted"] == "603703.26"
    assert reconciled["extracted_policies"][0]["asset_value"] == "0"
    assert reconciled["extracted_policies"][1]["asset_value"] == "603703.26"

    persisted = nodes.persist({**state, **reconciled})
    assert persisted["persisted_policies"] == 2
    assert persisted["persisted_obligations"] == 2

    with sessions() as session:
        values = session.scalars(select(PolicyValue).order_by(PolicyValue.policy_name)).all()
        assert len(values) == 1
        assert {v.policy_type for v in values} == {PolicyType.ULIP}
        assert sum((v.asset_value for v in values), start=Decimal("0")) == Decimal("603703.26")
        obligations = session.scalars(select(Obligation)).all()
        assert {o.due_date for o in obligations} == {date(2026, 9, 15), date(2026, 10, 1)}
        assert all(obligation.statement_id is not None for obligation in obligations)
        account = session.scalar(select(Account))
        assert account.account_type == AccountType.INSURANCE
        assert session.scalar(select(func.count()).select_from(Statement)) == 1
        assert session.scalar(select(Statement.file_name)) == "original-policy.pdf"


def test_premium_notice_creates_partial_contract_without_inventing_cash_value(config):
    sessions = _ledger_factory(config)
    nodes = Nodes(config, sessions)
    state = _base_state(
        policy_document_type="PREMIUM_NOTICE",
        extracted_policies=[{
            "policy_name": "TERM",
            "policy_type": PolicyType.TERM.value,
            "sum_assured": "300000",
            "premium_amount": "19700",
            "premium_due_date": "2026-01-01",
            "currency": "INR",
        }],
    )

    reconciled = nodes.reconcile(state)

    assert reconciled["reconcile_status"] == "ok"
    assert "complete policy statement" in " ".join(reconciled["policy_warnings"]).lower()
    assert "specific policy" in " ".join(reconciled["policy_warnings"]).lower()
    persisted = nodes.persist({**state, **reconciled})
    assert persisted["persisted_policies"] == 1
    assert persisted["persisted_obligations"] == 1
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(PolicyValue)) == 0
        contract = session.scalar(select(InsurancePolicy))
        assert contract is not None
        assert contract.evidence_status == "partial"
        assert contract.current_value_status == "not_provided"


def test_missing_endowment_surrender_value_keeps_contract_but_not_asset_value(config):
    sessions = _ledger_factory(config)
    nodes = Nodes(config, sessions)
    state = _base_state(
        file_hash="policy-hash-review",
        extracted_policies=[{
            "policy_name": "LIC Traditional Savings Plan",
            "policy_type": PolicyType.ENDOWMENT.value,
            "sum_assured": "1000000",
            "premium_amount": "60000",
            "currency": "INR",
        }],
    )

    reconciled = nodes.reconcile(state)
    assert reconciled["reconcile_status"] == "ok"
    assert "surrender" in " ".join(reconciled["policy_warnings"]).lower()

    # Missing current value must not become zero, but the policy contract is still useful.
    persisted = nodes.persist({**state, **reconciled})
    assert persisted["persisted_policies"] == 1
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(PolicyValue)) == 0
        assert session.scalar(select(func.count()).select_from(InsurancePolicy)) == 1
        assert session.scalar(select(func.count()).select_from(Statement)) == 1
