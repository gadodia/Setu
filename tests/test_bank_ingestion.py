"""Bank statements use a dedicated deterministic balance path."""

from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from setu.agents.ingestion_agent import IngestionAgent
from setu.agents.ingestion_agent import _guess_account_ref
from setu.agents.orchestrator import Orchestrator
from setu.extraction import detect_document_kind, extract_balance
from setu.graph.build import build_graph
from setu.graph.nodes import Nodes
from setu.models import Account, AccountType, Balance, Base
from setu.synthetic.statements import generate_statements
from setu.tools.pdf_extract import extract


class _NoModelCalls:
    def extract_structured(self, *args, **kwargs):
        raise AssertionError("Bank balance extraction must not call the language model")


def test_hdfc_bank_document_is_detected_and_balance_is_copied(config):
    paths = {path.stem: path for path in generate_statements(config)}
    text = extract(paths["hdfc_bank_bank"]).full_text

    assert detect_document_kind(text) == "BANK"
    balance = extract_balance(text)
    assert balance is not None
    assert balance.amount == "160000.00"
    assert balance.currency == "INR"
    assert balance.source_label == "Closing Balance"


def test_hdfc_bank_ingestion_reconciles_and_persists_balance(config):
    statement = {path.stem: path for path in generate_statements(config)}["hdfc_bank_bank"]
    engine = create_engine(config.db_url, future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    ingestion = IngestionAgent(config, client=_NoModelCalls())
    nodes = Nodes(config, sessions, ingestion_agent=ingestion)
    compiled = build_graph(
        config,
        session_factory=sessions,
        checkpoint_path=":memory:",
        nodes=nodes,
    )
    orchestrator = Orchestrator(config, compiled=compiled)
    try:
        outcome = orchestrator.ingest(str(statement), thread_id="bank-happy")
    finally:
        compiled.close()

    assert outcome.status == "completed"
    assert outcome.reconcile_status == "ok"
    assert outcome.persisted_balances == 1
    assert outcome.persisted_holdings == 0

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Balance)) == 1
        balance = session.scalar(select(Balance))
        account = session.scalar(select(Account))
        assert balance.amount == Decimal("160000.0000")
        assert account.account_type == AccountType.BANK


def _balance_certificate_table(words: str) -> list[list[list[str]]]:
    return [[
        [
            "AccountNumber/AccountTitle",
            "TypeofAccounts",
            "Limits",
            "Balanceinfigures (indicate debit or credit balance)",
            "Balanceinwords (indicate debit or credit balance)",
        ],
        [
            "12345678901234 Synthetic User",
            "SAVINGAccount",
            "INR 0",
            "INR 1,052,422.25 CreditBalance",
            words,
        ],
    ]]


def test_balance_certificate_uses_the_balance_column_and_words_check():
    text = (
        "Date:29-Aug-2026\nBalanceconfirmationcertificate\n"
        "AccountNumber/ TypeofAccounts Limits Balanceinfigures Balanceinwords"
    )
    tables = _balance_certificate_table(
        "INR TenLakhFiftyTwoThousandFourHundredAndTwentyTwoAndPaiseTwentyFiveOnlyCreditBalance"
    )

    assert detect_document_kind(text) == "BANK"
    balance = extract_balance(text, tables)

    assert balance is not None
    assert balance.amount == "1052422.25"
    assert balance.verification_amount == "1052422.25"
    assert balance.currency == "INR"
    assert _guess_account_ref(text, tables) == "****1234"


def test_balance_certificate_reconciliation_accepts_matching_words(config):
    nodes = Nodes(config, lambda: None)
    result = nodes.reconcile({
        "document_kind": "BANK",
        "extracted_balance": {
            "amount": "1052422.25",
            "currency": "INR",
            "source_label": "Balance in figures",
            "verification_amount": "1052422.25",
        },
        "raw_text": "",
    })

    assert result["reconcile_status"] == "ok"
    assert result["reconcile_delta"] == "0.00"


def test_balance_certificate_reconciliation_rejects_words_mismatch(config):
    nodes = Nodes(config, lambda: None)
    result = nodes.reconcile({
        "document_kind": "BANK",
        "extracted_balance": {
            "amount": "1052422.25",
            "currency": "INR",
            "source_label": "Balance in figures",
            "verification_amount": "1052422.24",
        },
        "raw_text": "",
    })

    assert result["reconcile_status"] == "mismatch"
    assert result["reconcile_delta"] == "0.01"


def test_bank_reconciliation_never_uses_an_account_number_as_total(config):
    nodes = Nodes(config, lambda: None)
    result = nodes.reconcile({
        "document_kind": "BANK",
        "extracted_balance": {
            "amount": "1052422.25",
            "currency": "INR",
            "source_label": "Balance in figures",
            "verification_amount": None,
        },
        "raw_text": "Account number 12345678901234",
    })

    assert result["reconcile_status"] == "mismatch"
    assert result["stated_total"] is None
