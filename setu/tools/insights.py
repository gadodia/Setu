"""Deterministic portfolio performance and attention signals.

The language model never calculates these figures. ROI is reported only for investment holdings
whose source explicitly supplied a cost basis or invested amount. Cash and insurance values are
excluded because their economics are different.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from setu.config import Config, load_config
from setu.models import InsurancePolicy, Obligation, PolicyType, RiskProfile, Statement
from setu.tools.calc import NetWorth, compute_net_worth
from setu.tools.fx import convert


@dataclass(frozen=True)
class InvestmentPerformance:
    status: str
    current_value: Decimal
    cost_basis: Decimal
    unrealized_gain: Decimal
    roi_fraction: Decimal | None
    coverage_fraction: Decimal
    covered_positions: int
    total_positions: int

    def as_dict(self) -> dict:
        return {
            key: (str(value) if isinstance(value, Decimal) else value)
            for key, value in asdict(self).items()
        }


@dataclass(frozen=True)
class PortfolioInsight:
    severity: str
    title: str
    detail: str
    evidence: dict[str, str]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthComponent:
    key: str
    label: str
    score: int
    max_score: int
    status: str
    detail: str
    evidence: dict[str, str]


@dataclass(frozen=True)
class RiskHorizon:
    status: str
    title: str
    detail: str
    evidence: dict[str, str]


@dataclass(frozen=True)
class HealthAction:
    priority: int
    category: str
    title: str
    detail: str


@dataclass(frozen=True)
class PortfolioHealth:
    score: int
    label: str
    as_of: str
    horizons: dict[str, RiskHorizon]
    components: list[HealthComponent]
    actions: list[HealthAction]
    missing_data: list[str]
    methodology: str

    def as_dict(self) -> dict:
        return asdict(self)


def compute_investment_performance(net_worth: NetWorth) -> InvestmentPerformance:
    """Aggregate document-backed holding cost basis into unrealized return."""
    holdings = [position for position in net_worth.positions if position.kind == "holding"]
    covered = [
        position
        for position in holdings
        if position.base_cost_basis is not None and position.base_cost_basis > 0
    ]
    total_holding_value = sum((position.base_value for position in holdings), Decimal("0"))
    current_value = sum((position.base_value for position in covered), Decimal("0"))
    cost_basis = sum(
        (position.base_cost_basis for position in covered if position.base_cost_basis is not None),
        Decimal("0"),
    )
    gain = current_value - cost_basis
    roi = gain / cost_basis if cost_basis > 0 else None
    coverage = current_value / total_holding_value if total_holding_value > 0 else Decimal("0")
    return InvestmentPerformance(
        status="available" if covered else "unavailable",
        current_value=current_value,
        cost_basis=cost_basis,
        unrealized_gain=gain,
        roi_fraction=roi,
        coverage_fraction=coverage,
        covered_positions=len(covered),
        total_positions=len(holdings),
    )


def compute_portfolio_health(
    session: Session,
    config: Config | None = None,
    *,
    net_worth: NetWorth | None = None,
    profile: RiskProfile | None = None,
    as_of: date | None = None,
) -> PortfolioHealth:
    """Build an explainable 0-100 diagnostic from deterministic ledger evidence.

    This is not a suitability assessment or a trade recommendation. It measures five observable
    dimensions: target alignment, position concentration, currency guardrail, short-term
    liquidity, and source completeness. A low score is a prompt for review, not a prediction.
    """
    config = config or load_config()
    nw = net_worth or compute_net_worth(session, config)
    profile = profile or session.scalar(select(RiskProfile).order_by(RiskProfile.id.desc()))
    analysis_date = as_of or date.today()

    if nw.total <= 0 or profile is None:
        missing = [] if profile is not None else ["A declared target allocation and currency guardrail"]
        return PortfolioHealth(
            score=0,
            label="Insufficient data",
            as_of=analysis_date.isoformat(),
            horizons={
                "current": RiskHorizon(
                    status="unknown",
                    title="Current risk cannot be scored",
                    detail="Add valued positions and a declared risk profile before comparing risk.",
                    evidence={},
                ),
                "short_term": RiskHorizon(
                    status="unknown",
                    title="Short-term resilience is unknown",
                    detail="Cash, obligations, and an emergency-reserve baseline are required.",
                    evidence={},
                ),
                "long_term": RiskHorizon(
                    status="unknown",
                    title="Long-term alignment is unknown",
                    detail="Target allocation and goal horizon data are required.",
                    evidence={},
                ),
            },
            components=[],
            actions=[],
            missing_data=missing,
            methodology="No score is meaningful without both valued assets and a declared profile.",
        )

    equity = nw.by_asset_class.get("EQUITY", Decimal("0"))
    debt = nw.by_asset_class.get("DEBT", Decimal("0"))
    cash = nw.by_asset_class.get("CASH", Decimal("0"))
    allocation_total = equity + debt + cash
    if allocation_total <= 0:
        allocation_total = nw.total
    actual = {
        "EQUITY": equity / allocation_total,
        "DEBT": debt / allocation_total,
        "CASH": cash / allocation_total,
    }
    targets = {
        "EQUITY": profile.target_equity,
        "DEBT": profile.target_debt,
        "CASH": profile.target_cash,
    }
    target_sum = sum(targets.values(), Decimal("0")) or Decimal("1")
    targets = {key: value / target_sum for key, value in targets.items()}
    allocation_distance = sum(
        (abs(actual[key] - targets[key]) for key in targets), Decimal("0")
    ) / Decimal("2")
    allocation_quality = _clamp(Decimal("1") - allocation_distance / Decimal("0.25"))

    holdings = [position for position in nw.positions if position.kind == "holding"]
    top = max(holdings, key=lambda item: item.base_value) if holdings else None
    top_share = Decimal("0") if top is None else top.base_value / allocation_total
    if top_share <= Decimal("0.15"):
        concentration_quality = Decimal("1")
    elif top_share >= Decimal("0.35"):
        concentration_quality = Decimal("0")
    else:
        concentration_quality = Decimal("1") - (
            (top_share - Decimal("0.15")) / Decimal("0.20")
        )

    usd_fraction = nw.by_currency.get("USD", Decimal("0")) / nw.total
    usd_limit = profile.max_usd_fraction
    if usd_limit is None or usd_fraction <= usd_limit:
        currency_quality = Decimal("1")
        currency_over = Decimal("0")
    else:
        currency_over = usd_fraction - usd_limit
        currency_quality = _clamp(Decimal("1") - currency_over / Decimal("0.30"))

    horizon_end = analysis_date + timedelta(days=365)
    obligations = session.scalars(
        select(Obligation)
        .outerjoin(Statement, Obligation.statement_id == Statement.id)
        .where(
            or_(Obligation.statement_id.is_(None), Statement.is_active.is_(True)),
            Obligation.due_date.is_not(None),
            Obligation.due_date <= horizon_end,
        )
    ).all()
    upcoming_obligations = sum(
        (convert(item.amount, item.currency, config) for item in obligations), Decimal("0")
    )
    cash_fraction = cash / allocation_total
    target_cash = targets["CASH"]
    cash_target_coverage = (
        Decimal("1") if target_cash <= 0 else _clamp(cash_fraction / target_cash)
    )
    obligation_coverage = (
        Decimal("1")
        if upcoming_obligations <= 0
        else _clamp(cash / upcoming_obligations)
    )
    liquidity_quality = (cash_target_coverage + obligation_coverage) / Decimal("2")

    performance = compute_investment_performance(nw)
    active_statements = session.scalars(
        select(Statement).where(Statement.is_active.is_(True))
    ).all()
    fresh_after = analysis_date - timedelta(days=180)
    freshness = (
        Decimal(sum(statement.period_end >= fresh_after for statement in active_statements))
        / Decimal(len(active_statements))
        if active_statements
        else Decimal("0")
    )
    policies = session.scalars(
        select(InsurancePolicy)
        .outerjoin(Statement, InsurancePolicy.statement_id == Statement.id)
        .where(or_(InsurancePolicy.statement_id.is_(None), Statement.is_active.is_(True)))
    ).all()
    value_bearing = [policy for policy in policies if policy.policy_type != PolicyType.TERM]
    policy_coverage = (
        Decimal(sum(policy.current_value_status == "verified" for policy in value_bearing))
        / Decimal(len(value_bearing))
        if value_bearing
        else Decimal("1")
    )
    data_quality = (
        performance.coverage_fraction * Decimal("0.50")
        + freshness * Decimal("0.25")
        + policy_coverage * Decimal("0.25")
    )

    components = [
        _component(
            "allocation", "Target alignment", 25, allocation_quality,
            f"About {allocation_distance * 100:.1f}% of investable assets would need to shift "
            "between equity, debt, and cash to match the declared target.",
            {
                "distance_fraction": str(allocation_distance),
                "actual_equity": str(actual["EQUITY"]),
                "target_equity": str(targets["EQUITY"]),
            },
        ),
        _component(
            "concentration", "Position concentration", 20, concentration_quality,
            (
                f"The largest holding, {top.label}, is {top_share * 100:.1f}% of investable assets."
                if top is not None else "No investment holding is available to measure."
            ),
            {"largest_position_fraction": str(top_share)},
        ),
        _component(
            "currency", "Currency exposure", 15, currency_quality,
            (
                f"USD exposure is {usd_fraction * 100:.1f}% versus the declared "
                f"{usd_limit * 100:.1f}% maximum."
                if usd_limit is not None
                else "No currency guardrail is declared."
            ),
            {"usd_fraction": str(usd_fraction), "over_limit_fraction": str(currency_over)},
        ),
        _component(
            "liquidity", "Short-term liquidity", 20, liquidity_quality,
            f"Cash is {cash_fraction * 100:.1f}% of investable assets versus a "
            f"{target_cash * 100:.1f}% target and covers {obligation_coverage * 100:.1f}% "
            "of known obligations due within 12 months.",
            {
                "cash_fraction": str(cash_fraction),
                "target_cash_fraction": str(target_cash),
                "known_obligations_base": str(upcoming_obligations),
                "obligation_coverage_fraction": str(obligation_coverage),
            },
        ),
        _component(
            "data", "Data completeness", 20, data_quality,
            f"Cost-basis coverage is {performance.coverage_fraction * 100:.1f}%, source "
            f"freshness is {freshness * 100:.1f}%, and current-value coverage for "
            f"valuation-bearing policies is {policy_coverage * 100:.1f}%.",
            {
                "cost_basis_coverage_fraction": str(performance.coverage_fraction),
                "fresh_source_fraction": str(freshness),
                "policy_value_coverage_fraction": str(policy_coverage),
            },
        ),
    ]
    score = sum(component.score for component in components)
    label = (
        "Strong" if score >= 80 else
        "Stable" if score >= 65 else
        "Watch" if score >= 50 else
        "Needs attention"
    )
    current_status = (
        "aligned" if score >= 80 else "moderate" if score >= 65 else
        "watch" if score >= 50 else "elevated"
    )
    short_status = (
        "elevated"
        if cash_target_coverage < Decimal("0.50") or obligation_coverage < Decimal("1")
        else "watch"
        if cash_target_coverage < Decimal("1")
        else "stable"
    )
    long_status = (
        "elevated"
        if allocation_distance > Decimal("0.10")
        or top_share > Decimal("0.25")
        or currency_over > Decimal("0.10")
        else "watch"
        if allocation_distance > Decimal("0.05")
        else "aligned"
    )

    missing_data = [
        "Monthly essential expenses and an emergency-reserve goal",
        "Future goal dates, amounts, and spending currencies",
        "Liabilities, income stability, dependents, and tax constraints",
    ]
    if policy_coverage < 1:
        missing_data.append("A current surrender or fund-value statement for every savings policy")

    actions: list[HealthAction] = []
    if short_status != "stable":
        actions.append(HealthAction(
            1, "short_term", "Review the near-term cash buffer",
            "Compare known obligations with cash and add monthly essential expenses before "
            "setting an emergency-reserve amount.",
        ))
    if allocation_distance > Decimal("0.05"):
        actions.append(HealthAction(
            2, "long_term", "Plan how to reduce allocation drift",
            "Review whether future contributions or a separately approved rebalance can move "
            "equity, debt, and cash toward the declared target. Consider taxes and lockups first.",
        ))
    if top_share > Decimal("0.20") and top is not None:
        actions.append(HealthAction(
            3, "long_term", "Review the largest single position",
            f"Decide whether {top.label}'s {top_share * 100:.1f}% share is consistent with the "
            "declared risk profile; Setu will not sell or recommend a security.",
        ))
    if currency_over > 0:
        actions.append(HealthAction(
            4, "long_term", "Match currency exposure to future spending",
            "Record which goals and liabilities are expected in USD versus INR before changing "
            "the currency mix.",
        ))
    if policy_coverage < 1:
        actions.append(HealthAction(
            5, "data", "Close the policy valuation gap",
            "Upload a current surrender-value, bonus, or fund-value statement for the policy "
            "whose current asset value is still unknown.",
        ))

    return PortfolioHealth(
        score=score,
        label=label,
        as_of=analysis_date.isoformat(),
        horizons={
            "current": RiskHorizon(
                current_status,
                f"Current portfolio: {label.lower()}",
                f"The explainable health score is {score}/100 across allocation, concentration, "
                "currency, liquidity, and data completeness.",
                {"score": str(score)},
            ),
            "short_term": RiskHorizon(
                short_status,
                "Short-term liquidity",
                f"Cash covers {obligation_coverage * 100:.1f}% of known obligations due within "
                "12 months; living-expense coverage remains unknown.",
                {
                    "cash_base": str(cash),
                    "known_obligations_base": str(upcoming_obligations),
                },
            ),
            "long_term": RiskHorizon(
                long_status,
                "Long-term portfolio alignment",
                f"Equity is {actual['EQUITY'] * 100:.1f}% versus a {targets['EQUITY'] * 100:.1f}% "
                f"target, the largest holding is {top_share * 100:.1f}%, and USD exposure is "
                f"{usd_fraction * 100:.1f}%.",
                {
                    "allocation_distance_fraction": str(allocation_distance),
                    "largest_position_fraction": str(top_share),
                    "usd_fraction": str(usd_fraction),
                },
            ),
        },
        components=components,
        actions=actions,
        missing_data=missing_data,
        methodology=(
            "A deterministic diagnostic, not investment advice: 25 points for target alignment, "
            "20 concentration, 15 currency, 20 liquidity, and 20 data completeness."
        ),
    )


def _clamp(value: Decimal) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), value))


def _component(
    key: str,
    label: str,
    max_score: int,
    quality: Decimal,
    detail: str,
    evidence: dict[str, str],
) -> HealthComponent:
    score = int(
        (Decimal(max_score) * _clamp(quality)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    ratio = Decimal(score) / Decimal(max_score)
    status = "strong" if ratio >= Decimal("0.80") else "watch" if ratio >= Decimal("0.50") else "attention"
    return HealthComponent(key, label, score, max_score, status, detail, evidence)


def build_portfolio_insights(
    session: Session,
    config: Config | None = None,
    *,
    net_worth: NetWorth | None = None,
    profile: RiskProfile | None = None,
) -> list[PortfolioInsight]:
    """Return a short, ranked list of evidence-backed portfolio observations."""
    config = config or load_config()
    nw = net_worth or compute_net_worth(session, config)
    profile = profile or session.scalar(select(RiskProfile).order_by(RiskProfile.id.desc()))
    performance = compute_investment_performance(nw)
    insights: list[PortfolioInsight] = []

    if performance.status == "available":
        direction = "gain" if performance.unrealized_gain >= 0 else "loss"
        insights.append(PortfolioInsight(
            severity="positive" if performance.unrealized_gain >= 0 else "attention",
            title=f"Document-backed investment {direction}",
            detail=(
                "Current value is compared only with source-stated cost basis. "
                "Cash, insurance, taxes, fees, and distributions are not included."
            ),
            evidence={
                "current_value": str(performance.current_value),
                "cost_basis": str(performance.cost_basis),
                "unrealized_gain": str(performance.unrealized_gain),
                "roi_fraction": str(performance.roi_fraction),
            },
        ))

    if performance.total_positions and performance.covered_positions < performance.total_positions:
        missing = performance.total_positions - performance.covered_positions
        insights.append(PortfolioInsight(
            severity="data_gap",
            title="ROI coverage is incomplete",
            detail=(
                f"{missing} investment position(s) have no source-stated cost basis. "
                "Setu leaves their return unknown instead of estimating it."
            ),
            evidence={"coverage_fraction": str(performance.coverage_fraction)},
        ))

    if nw.total > 0 and nw.positions:
        top = max(nw.positions, key=lambda position: position.base_value)
        share = top.base_value / nw.total
        insights.append(PortfolioInsight(
            severity="attention" if share > Decimal("0.25") else "info",
            title=f"Largest position: {top.label}",
            detail=f"This position represents {share * 100:.1f}% of current net worth.",
            evidence={"share_fraction": str(share), "base_value": str(top.base_value)},
        ))

    if nw.total > 0 and profile is not None and profile.max_usd_fraction is not None:
        usd_fraction = nw.by_currency.get("USD", Decimal("0")) / nw.total
        limit = profile.max_usd_fraction
        over = usd_fraction - limit
        insights.append(PortfolioInsight(
            severity="attention" if over > 0 else "positive",
            title=(
                "USD exposure exceeds your guardrail"
                if over > 0
                else "USD exposure is within your guardrail"
            ),
            detail=(
                f"USD exposure is {usd_fraction * 100:.1f}% versus your "
                f"{limit * 100:.1f}% maximum."
            ),
            evidence={
                "actual_fraction": str(usd_fraction),
                "maximum_fraction": str(limit),
            },
        ))

    if nw.total > 0 and profile is not None:
        targets = {
            "EQUITY": profile.target_equity,
            "DEBT": profile.target_debt,
            "CASH": profile.target_cash,
        }
        drift = {
            asset_class: nw.by_asset_class.get(asset_class, Decimal("0")) / nw.total - target
            for asset_class, target in targets.items()
        }
        asset_class, delta = max(drift.items(), key=lambda item: abs(item[1]))
        direction = "above" if delta > 0 else "below"
        insights.append(PortfolioInsight(
            severity="attention" if abs(delta) > Decimal("0.05") else "info",
            title=f"Largest allocation drift: {asset_class.title()}",
            detail=f"{asset_class.title()} is {abs(delta) * 100:.1f} percentage points {direction} target.",
            evidence={"drift_fraction": str(delta), "target_fraction": str(targets[asset_class])},
        ))

    incomplete_policies = session.scalar(
        select(InsurancePolicy.id)
        .outerjoin(Statement, InsurancePolicy.statement_id == Statement.id)
        .where(
            or_(InsurancePolicy.statement_id.is_(None), Statement.is_active.is_(True)),
            InsurancePolicy.current_value_status == "not_provided",
        )
        .limit(1)
    )
    if incomplete_policies is not None:
        insights.append(PortfolioInsight(
            severity="data_gap",
            title="A policy has no current cash value",
            detail=(
                "It remains in coverage details but is excluded from net worth until a source "
                "states surrender or fund value."
            ),
            evidence={"valuation_policy": "fail_closed"},
        ))

    stale_before = date.today() - timedelta(days=180)
    stale_source = session.scalar(
        select(Statement.id)
        .where(Statement.is_active.is_(True), Statement.period_end < stale_before)
        .limit(1)
    )
    if stale_source is not None:
        insights.append(PortfolioInsight(
            severity="data_gap",
            title="Some portfolio data is over 180 days old",
            detail="Upload a newer statement before relying on the current allocation or return.",
            evidence={"stale_before": stale_before.isoformat()},
        ))

    severity_order = {"attention": 0, "data_gap": 1, "positive": 2, "info": 3}
    return sorted(insights, key=lambda item: severity_order.get(item.severity, 9))[:6]
