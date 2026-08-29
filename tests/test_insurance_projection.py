"""Source-backed insurance calculations remain deterministic and explicit."""

from decimal import Decimal

from setu.insurance import calculate_maturity_outlook


def test_lic_plan_75_calculates_grounded_maturity_and_lifetime_benefits():
    projection = calculate_maturity_outlook(
        policy_name="The Money Back Policy - 20 Years",
        plan_number=None,
        sum_assured=Decimal("300000"),
        vested_bonus=None,
        guaranteed_additions=Decimal("183000"),
        policy_term_years=20,
        premium_payment_term_years=20,
        maturity_date="2030-01-15",
    )

    assert projection is not None
    assert projection["status"] == "calculated_plan_rule"
    assert Decimal(projection["base_maturity_amount"]) == Decimal("120000")
    assert Decimal(projection["scheduled_prior_benefits"]) == Decimal("180000")
    assert Decimal(projection["amount"]) == Decimal("303000")
    assert Decimal(projection["grounded_lifetime_benefits"]) == Decimal("483000")
    assert projection["future_bonus_included"] is False


def test_plan_rule_does_not_guess_for_a_similarly_named_unverified_policy():
    projection = calculate_maturity_outlook(
        policy_name="Money Back Policy",
        plan_number=None,
        sum_assured=Decimal("300000"),
        vested_bonus=None,
        guaranteed_additions=None,
        policy_term_years=20,
        premium_payment_term_years=None,
    )

    assert projection is None
