"""Reversible source controls for portfolio calculations and dashboard data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from setu.dashboard.server import _source_inventory, create_app
from setu.db import _ensure_compatibility_columns
from setu.models import (
    Account,
    AccountType,
    AssetClass,
    Base,
    Geography,
    Holding,
    InsurancePolicy,
    Institution,
    Obligation,
    PolicyType,
    PolicyValue,
    Statement,
)
from setu.tools.calc import compute_net_worth


def _account(session) -> Account:
    institution = Institution(name="Fidelity", geography=Geography.US)
    account = Account(
        institution=institution,
        name="Brokerage",
        account_type=AccountType.BROKERAGE,
        currency="USD",
        account_ref="****1234",
    )
    session.add(account)
    session.flush()
    return account


def _statement(session, *, file_name: str, file_hash: str, period_end: date) -> Statement:
    statement = Statement(
        institution="Fidelity",
        account_ref="****1234",
        file_name=file_name,
        file_hash=file_hash,
        period_end=period_end,
    )
    session.add(statement)
    session.flush()
    return statement


def test_inactive_latest_source_falls_back_to_previous_active_snapshot(session, config):
    account = _account(session)
    older = _statement(
        session,
        file_name="january.pdf",
        file_hash="source-january",
        period_end=date(2026, 1, 31),
    )
    newer = _statement(
        session,
        file_name="february.pdf",
        file_hash="source-february",
        period_end=date(2026, 2, 28),
    )
    session.add_all([
        Holding(
            account_id=account.id,
            statement_id=older.id,
            symbol="VOO",
            name="Vanguard S&P 500",
            asset_class=AssetClass.EQUITY,
            geography=Geography.US,
            market_value=Decimal("100"),
            currency="USD",
            as_of_date=older.period_end,
        ),
        Holding(
            account_id=account.id,
            statement_id=newer.id,
            symbol="VOO",
            name="Vanguard S&P 500",
            asset_class=AssetClass.EQUITY,
            geography=Geography.US,
            market_value=Decimal("125"),
            currency="USD",
            as_of_date=newer.period_end,
        ),
    ])
    session.commit()

    assert compute_net_worth(session, config).total == Decimal("125")
    inventory = {
        source["file_name"]: source for source in _source_inventory(session, config)["sources"]
    }
    assert inventory["january.pdf"]["status"] == "available"
    assert inventory["january.pdf"]["used_in_portfolio"] is False
    assert inventory["february.pdf"]["status"] == "included"

    newer.is_active = False
    session.commit()
    assert compute_net_worth(session, config).total == Decimal("100")
    inventory = {
        source["file_name"]: source for source in _source_inventory(session, config)["sources"]
    }
    assert inventory["january.pdf"]["status"] == "included"
    assert inventory["february.pdf"]["status"] == "inactive"

    older.is_active = False
    session.commit()
    assert compute_net_worth(session, config).total == Decimal("0")

    newer.is_active = True
    session.commit()
    assert compute_net_worth(session, config).total == Decimal("125")


def _dashboard_client(config):
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with sessions() as session:
        institution = Institution(name="LIC", geography=Geography.INDIA)
        account = Account(
            institution=institution,
            name="LIC policy",
            account_type=AccountType.INSURANCE,
            currency="INR",
            account_ref="****1700",
        )
        source = Statement(
            institution="LIC",
            account_ref="****1700",
            file_name="lic-policy.pdf",
            file_hash="source-lic-policy",
            period_end=date(2026, 7, 31),
        )
        session.add_all([account, source])
        session.flush()
        session.add_all([
            InsurancePolicy(
                account_id=account.id,
                statement_id=source.id,
                policy_name="LIC New Endowment Plan",
                policy_type=PolicyType.ENDOWMENT,
                sum_assured=Decimal("1000000"),
                currency="INR",
                document_type="POLICY_STATEMENT",
                evidence_status="complete",
                current_value_status="verified",
            ),
            PolicyValue(
                account_id=account.id,
                statement_id=source.id,
                policy_name="LIC New Endowment Plan",
                policy_type=PolicyType.ENDOWMENT,
                sum_assured=Decimal("1000000"),
                asset_value=Decimal("500000"),
                currency="INR",
                as_of_date=source.period_end,
            ),
            Obligation(
                account_id=account.id,
                statement_id=source.id,
                description="Premium: LIC New Endowment Plan",
                amount=Decimal("25000"),
                currency="INR",
                recurring=True,
            ),
        ])
        session.commit()
    client = TestClient(create_app(config=config, session_factory=sessions))
    response = client.post(
        "/api/auth/login",
        json={"password": config.dashboard_password.get_secret_value()},
    )
    assert response.status_code == 200
    return client


def test_dashboard_can_deactivate_and_reactivate_every_record_from_a_source(config):
    client = _dashboard_client(config)
    token = client.get("/api/session").json()["request_token"]

    inventory = client.get("/api/sources").json()
    source = inventory["sources"][0]
    assert source["active"] is True
    assert source["used_in_portfolio"] is True
    assert source["records"]["policies"] == 1
    assert source["records"]["obligations"] == 1
    assert Decimal(client.get("/api/overview").json()["net_worth"]) > 0
    assert len(client.get("/api/policies").json()["policies"]) == 1

    forbidden = client.patch(f"/api/sources/{source['id']}", json={"active": False})
    assert forbidden.status_code == 403

    disabled = client.patch(
        f"/api/sources/{source['id']}",
        headers={"X-Setu-Request-Token": token},
        json={"active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["source"]["status"] == "inactive"

    overview = client.get("/api/overview").json()
    assert Decimal(overview["net_worth"]) == Decimal("0")
    assert overview["counts"] == {
        "accounts": 0,
        "holdings": 0,
        "balances": 0,
        "policies": 0,
        "obligations": 0,
    }
    assert client.get("/api/policies").json()["policies"] == []

    enabled = client.patch(
        f"/api/sources/{source['id']}",
        headers={"X-Setu-Request-Token": token},
        json={"active": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["source"]["status"] == "included"
    assert Decimal(client.get("/api/overview").json()["net_worth"]) > 0
    assert len(client.get("/api/policies").json()["policies"]) == 1


def test_existing_sqlite_ledger_gets_additive_source_control_columns(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE statements (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE insurance_policies ("
            "id INTEGER PRIMARY KEY, account_id INTEGER, statement_id INTEGER, policy_name TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE obligations ("
            "id INTEGER PRIMARY KEY, account_id INTEGER, description TEXT)"
        )
        connection.exec_driver_sql("INSERT INTO statements (id) VALUES (7), (8), (9)")
        connection.exec_driver_sql(
            "INSERT INTO insurance_policies "
            "(id, account_id, statement_id, policy_name) "
            "VALUES (1, 3, 7, 'LIC New Endowment Plan')"
        )
        connection.exec_driver_sql(
            "INSERT INTO obligations (id, account_id, description) "
            "VALUES (1, 3, 'Premium: LIC New Endowment Plan')"
        )
        connection.exec_driver_sql(
            "INSERT INTO insurance_policies "
            "(id, account_id, statement_id, policy_name) VALUES "
            "(2, 4, 8, 'Repeated Policy'), (3, 4, 9, 'Repeated Policy')"
        )
        connection.exec_driver_sql(
            "INSERT INTO obligations (id, account_id, description) "
            "VALUES (2, 4, 'Premium: Repeated Policy')"
        )

    _ensure_compatibility_columns(engine)
    _ensure_compatibility_columns(engine)

    with engine.connect() as connection:
        assert {column["name"] for column in inspect(connection).get_columns("statements")} >= {
            "id",
            "is_active",
        }
        assert {column["name"] for column in inspect(connection).get_columns("obligations")} >= {
            "id",
            "statement_id",
        }
        assert connection.exec_driver_sql(
            "SELECT is_active FROM statements WHERE id = 7"
        ).scalar_one() == 1
        assert connection.exec_driver_sql(
            "SELECT statement_id FROM obligations WHERE id = 1"
        ).scalar_one() == 7
        assert connection.exec_driver_sql(
            "SELECT statement_id FROM obligations WHERE id = 2"
        ).scalar_one() is None
