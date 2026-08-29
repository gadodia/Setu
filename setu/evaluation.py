"""Repeatable safety and correctness evaluation for the final Setu demo."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from time import perf_counter

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from setu.agents.ingestion_agent import IngestionAgent
from setu.agents.reconciliation_agent import ReconciliationAgent
from setu.config import Config, load_config
from setu.extraction import detect_document_kind, extract_balance
from setu.models import AccountType, Base, InsurancePolicy, PolicyType, PolicyValue
from setu.synthetic.generate import seed_portfolio
from setu.synthetic.spec import AS_OF, PORTFOLIO
from setu.synthetic.statements import generate_statements
from setu.tools.calc import compute_net_worth
from setu.tools.insights import compute_investment_performance, compute_portfolio_health
from setu.tools.pdf_extract import extract
from setu.tools.registry import TOOL_SCHEMAS


@dataclass(frozen=True)
class EvaluationMetric:
    name: str
    value: str
    target: str
    passed: bool
    note: str


@dataclass(frozen=True)
class EvaluationReport:
    metrics: list[EvaluationMetric]
    elapsed_seconds: float

    @property
    def passed(self) -> bool:
        return all(metric.passed for metric in self.metrics)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "metrics": [asdict(metric) for metric in self.metrics],
        }


def run_evaluation(
    config: Config | None = None,
    *,
    live_model: bool = False,
) -> EvaluationReport:
    """Run a synthetic-only evaluation without touching the user's ledger."""
    started = perf_counter()
    config = config or load_config()
    paths = generate_statements(config)
    path_by_stem = {path.stem: path for path in paths}
    metrics: list[EvaluationMetric] = []

    expected_kinds = {
        "fidelity_brokerage": "HOLDINGS",
        "fidelity_401k": "HOLDINGS",
        "cams_mf_folio": "HOLDINGS",
        "hdfc_bank_bank": "BANK",
        "tata_aia_life_insurance": "POLICY",
        "lic_of_india_insurance": "POLICY",
    }
    detected = {
        stem: detect_document_kind(extract(path_by_stem[stem]).full_text)
        for stem in expected_kinds
    }
    kind_matches = sum(detected[stem] == expected for stem, expected in expected_kinds.items())
    metrics.append(EvaluationMetric(
        name="Document classification accuracy",
        value=f"{kind_matches}/{len(expected_kinds)}",
        target=f"{len(expected_kinds)}/{len(expected_kinds)}",
        passed=kind_matches == len(expected_kinds),
        note="Brokerage, 401(k), CAS, bank, ULIP/term, and endowment synthetic PDFs.",
    ))

    reconciler = ReconciliationAgent(config)
    reconciled = 0
    eligible = 0
    for account in PORTFOLIO:
        if account.account_type == AccountType.INSURANCE:
            continue
        stem = _statement_stem(account.account_type, account.institution)
        text = extract(path_by_stem[stem]).full_text
        expected_total = (
            account.balance
            if account.balance is not None
            else sum((holding.market_value for holding in account.holdings), Decimal("0"))
        )
        eligible += 1
        reconciled += reconciler.run(text, expected_total).status == "ok"
    metrics.append(EvaluationMetric(
        name="Golden reconciliation pass rate",
        value=f"{reconciled}/{eligible}",
        target=f"{eligible}/{eligible}",
        passed=reconciled == eligible,
        note="Expected totals are derived independently from the canonical synthetic portfolio.",
    ))

    mismatch_text = extract(path_by_stem["fidelity_brokerage"]).full_text
    escalation = reconciler.run(mismatch_text, Decimal("100000")).status == "mismatch"
    metrics.append(EvaluationMetric(
        name="Mismatch escalation trigger",
        value="triggered" if escalation else "missed",
        target="triggered",
        passed=escalation,
        note="A material under-extraction must route to review instead of persistence.",
    ))

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with sessions() as session:
        seed_portfolio(session, config)
        net_worth = compute_net_worth(session, config)
        expected_net_worth = _expected_net_worth(config)
        error = abs(net_worth.total - expected_net_worth)
        metrics.append(EvaluationMetric(
            name="Net-worth ground-truth error",
            value=str(error),
            target="0",
            passed=error == 0,
            note="Exact Decimal aggregation across USD and INR.",
        ))

        performance = compute_investment_performance(net_worth)
        metrics.append(EvaluationMetric(
            name="ROI evidence coverage",
            value=(
                f"{performance.covered_positions}/{performance.total_positions} positions; "
                f"{performance.coverage_fraction * 100:.1f}% of investment value"
            ),
            target="100.0% for demo corpus",
            passed=performance.coverage_fraction == Decimal("1"),
            note="ROI remains unknown for any holding without source-stated cost basis.",
        ))

        term_contracts = session.scalars(
            select(InsurancePolicy).where(InsurancePolicy.policy_type == PolicyType.TERM)
        ).all()
        unsafe_term_values = session.scalars(
            select(PolicyValue).where(PolicyValue.policy_type == PolicyType.TERM)
        ).all()
        unsafe_terms = sum(value.asset_value != 0 for value in unsafe_term_values)
        metrics.append(EvaluationMetric(
            name="Unsupported term-policy valuation rate",
            value=f"{unsafe_terms}/{len(term_contracts)}",
            target="0 unsafe valuations",
            passed=unsafe_terms == 0,
            note="Term coverage is shown but never counted as an asset.",
        ))

        health = compute_portfolio_health(
            session,
            config,
            net_worth=net_worth,
            as_of=AS_OF,
        )
        horizon_statuses = {name: horizon.status for name, horizon in health.horizons.items()}
        metrics.append(EvaluationMetric(
            name="Explainable risk-scenario coverage",
            value=(
                f"{len(health.components)} components; "
                + ", ".join(f"{name}={status}" for name, status in horizon_statuses.items())
            ),
            target="current, short_term, and long_term all evaluated",
            passed=(
                len(health.components) == 5
                and set(horizon_statuses) == {"current", "short_term", "long_term"}
                and all(status != "unknown" for status in horizon_statuses.values())
            ),
            note="The score is deterministic and includes actions plus explicit missing data.",
        ))

    serialized_tools = str(TOOL_SCHEMAS).lower()
    raw_tool_exposed = "pdf_extract" in serialized_tools or '"path"' in serialized_tools
    metrics.append(EvaluationMetric(
        name="Raw-document cloud tool exposure",
        value="exposed" if raw_tool_exposed else "none",
        target="none",
        passed=not raw_tool_exposed,
        note="Claude receives sanitized ledger calculations, never PDF text or filesystem paths.",
    ))

    if live_model:
        extraction_agent = IngestionAgent(config)
        exact = 0
        expected_positions = 0
        for account in PORTFOLIO:
            if not account.holdings:
                continue
            stem = _statement_stem(account.account_type, account.institution)
            result = extraction_agent.run(str(path_by_stem[stem]))
            actual = {
                (holding.name, holding.as_decimal("market_value"), holding.as_decimal("cost_basis"))
                for holding in result.holdings
            }
            expected = {
                (holding.name, holding.market_value, holding.cost_basis)
                for holding in account.holdings
            }
            exact += len(actual & expected)
            expected_positions += len(expected)
        metrics.append(EvaluationMetric(
            name="Live local-model holding accuracy",
            value=f"{exact}/{expected_positions}",
            target=f"{expected_positions}/{expected_positions}",
            passed=exact == expected_positions,
            note="Exact name, current value, and document-backed cost basis on the demo corpus.",
        ))

    return EvaluationReport(metrics=metrics, elapsed_seconds=perf_counter() - started)


def _statement_stem(account_type: AccountType, institution: str) -> str:
    institution_slug = institution.split("(")[0].strip().lower().replace(" ", "_")
    return f"{institution_slug}_{account_type.value.lower()}"


def _expected_net_worth(config: Config) -> Decimal:
    total = Decimal("0")
    for account in PORTFOLIO:
        rate = config.fx_rates[account.currency]
        total += sum((holding.market_value * rate for holding in account.holdings), Decimal("0"))
        if account.balance is not None:
            total += account.balance * rate
        total += sum(
            (
                policy.asset_value * rate
                for policy in account.policies
                if policy.asset_value is not None
            ),
            Decimal("0"),
        )
    return total
