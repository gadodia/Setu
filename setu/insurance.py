"""Deterministic, source-backed insurance benefit calculations.

These rules calculate contract benefits from extracted evidence. They do not estimate surrender
value, future bonuses, or investment returns. Product rules must be narrow enough to identify the
official plan unambiguously and must expose their assumptions to the caller.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


LIC_PLAN_75_SOURCE = (
    "LIC Money Back Plan (Table No. 75) official benefit illustration"
)


def calculate_maturity_outlook(
    *,
    policy_name: str,
    plan_number: str | None,
    sum_assured: Decimal | None,
    vested_bonus: Decimal | None,
    guaranteed_additions: Decimal | None,
    policy_term_years: int | None,
    premium_payment_term_years: int | None,
    maturity_date: Any = None,
) -> dict[str, Any] | None:
    """Return a grounded product-rule calculation, or ``None`` when no exact rule matches."""
    if not _is_lic_money_back_plan_75(
        policy_name,
        plan_number,
        policy_term_years,
        premium_payment_term_years,
    ):
        return None
    if sum_assured is None:
        return None

    base_maturity = sum_assured * Decimal("0.40")
    scheduled_prior_benefits = sum_assured * Decimal("0.60")
    declared_bonus_additions = (vested_bonus or Decimal("0")) + (
        guaranteed_additions or Decimal("0")
    )
    grounded_maturity = base_maturity + declared_bonus_additions
    grounded_lifetime = sum_assured + declared_bonus_additions
    return {
        "status": "calculated_plan_rule",
        "amount": str(grounded_maturity),
        "base_maturity_amount": str(base_maturity),
        "declared_bonus_additions": str(declared_bonus_additions),
        "scheduled_prior_benefits": str(scheduled_prior_benefits),
        "grounded_lifetime_benefits": str(grounded_lifetime),
        "maturity_date": None if maturity_date is None else str(maturity_date),
        "method": (
            "40% of sum assured at year 20, plus declared bonuses/additions currently shown"
        ),
        "rule_source": LIC_PLAN_75_SOURCE,
        "future_bonus_included": False,
        "guaranteed": None,
        "assumptions": [
            "The exact product is LIC Money Back Plan 75.",
            "The policy remains in force through maturity.",
            "The displayed bonus/additions are vested and payable at maturity.",
            "Scheduled 5th, 10th, and 15th year survival benefits were paid when due.",
            "Future bonuses and any Final Additional Bonus are excluded.",
        ],
        "missing_fields": [],
    }


def _is_lic_money_back_plan_75(
    policy_name: str,
    plan_number: str | None,
    policy_term_years: int | None,
    premium_payment_term_years: int | None,
) -> bool:
    if plan_number == "75":
        return True
    normalized = " ".join(policy_name.lower().replace("years", "").split()).strip(" -")
    return (
        "the money back policy - 20" in normalized
        and policy_term_years == 20
        and premium_payment_term_years == 20
    )
