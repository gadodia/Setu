"""Policy-document routing and deterministic insurance valuation."""

from decimal import Decimal

import setu.extraction as extraction
from setu.agents.ingestion_agent import IngestionAgent
from setu.models import PolicyType
from setu.synthetic.statements import generate_statements


def _policy_api():
    detect = getattr(extraction, "detect_document_kind", None)
    policy_model = getattr(extraction, "ExtractedPolicy", None)
    value_policy = getattr(extraction, "value_policy", None)
    assert detect is not None, "policy document detection is not implemented"
    assert policy_model is not None, "policy extraction schema is not implemented"
    assert value_policy is not None, "deterministic policy valuation is not implemented"
    return detect, policy_model, value_policy


def test_detects_lic_policy_document_without_misrouting_brokerage_statement():
    detect, _, _ = _policy_api()

    lic_text = """
    LIFE INSURANCE CORPORATION OF INDIA
    Policy Number 123456789  Life Assured SYNTHETIC PERSON
    Basic Sum Assured Rs. 10,00,000
    Current Surrender Value Rs. 2,45,000
    Premium Due Date 15-Sep-2026
    """
    brokerage_text = """
    Fidelity Investments Brokerage Statement
    Account X1234  June 30, 2026
    Symbol  Quantity  Market Value
    VTI     10        $3,100.00
    """

    assert detect(lic_text) == "POLICY"
    assert detect(brokerage_text) == "HOLDINGS"


def test_detects_ulip_policy_document():
    detect, _, _ = _policy_api()
    text = """
    Tata AIA Life Insurance
    Policy No. ULIP-9988
    Fund Name Whole Life Mid Cap Equity Fund
    Total Units 12,345.67  NAV 48.90  Fund Value INR 603,703.26
    Premium Amount INR 50,000
    """
    assert detect(text) == "POLICY"


def test_renewal_premium_notice_is_not_treated_as_a_complete_policy_statement():
    detect_subtype = getattr(extraction, "detect_policy_document_type", None)
    identity_issues = getattr(extraction, "policy_identity_issues", None)
    assert detect_subtype is not None
    assert identity_issues is not None
    text = """
    LIFE INSURANCE CORPORATION OF INDIA
    RENEWAL PREMIUM NOTICE
    Policy Number 86918612  Plan TERM
    Sum Assured INR 300000  Renewal Premium INR 19700
    """
    policy = extraction.ExtractedPolicy(
        policy_name="TERM",
        policy_type=PolicyType.TERM,
        sum_assured="300000",
        premium_amount="19700",
        currency="INR",
    )

    subtype = detect_subtype(text)
    issues = identity_issues(policy, subtype)

    assert subtype == "PREMIUM_NOTICE"
    assert any("not a complete policy statement" in issue.lower() for issue in issues)
    assert any("specific policy or product name" in issue.lower() for issue in issues)


def test_policy_schema_captures_projection_evidence_without_calculating_it():
    policy = extraction.ExtractedPolicy(
        policy_name="LIC New Endowment Plan",
        policy_type=PolicyType.ENDOWMENT,
        plan_number="914",
        sum_assured="300000",
        commencement_date="2014-01-01",
        maturity_date="2034-01-01",
        policy_term_years=20,
        premium_payment_term_years=15,
        premium_amount="19700",
        vested_bonus="120000",
        maturity_benefit_4pct="505000",
        maturity_benefit_8pct="690000",
        currency="INR",
    )

    assert policy.plan_number == "914"
    assert policy.maturity_date == "2034-01-01"
    assert policy.maturity_benefit_4pct == "505000"
    assert policy.maturity_benefit_8pct == "690000"


def test_labelled_lic_fields_override_incomplete_local_model_output():
    text = """
    Life Insurance Corporation of India
    Detailed Policy Status Report
    Policy Number: 578351700
    Plan Name: The Money Back Policy - 20 Policy Status: In Force
    Years
    Instalment Premium: ₹ 18,659.00
    Sum Assured: ₹ 3,00,000 Premium due from: 15/01/2027
    Bonus, Guranteed ₹ 183000.0 Addition
    Premium Mode: Yearly
    Policy Term: 20
    Commencement Date: 15/01/2010 Premium Paying Term: 20
    Date of Maturity: 15/01/2030
    """

    class IncompleteLocalModel:
        def extract_structured(self, _prompt, schema, system=None):
            return schema(policies=[extraction.ExtractedPolicy(
                policy_name="The Money Back Policy - 20",
                policy_type=PolicyType.ENDOWMENT,
                plan_number="578351700",
                currency="INR",
            )])

    result = extraction.extract_policies(text, client=IncompleteLocalModel())
    policy = result.policies[0]

    assert policy.policy_number == "****1700"
    assert policy.plan_number is None
    assert policy.policy_name == "The Money Back Policy - 20 Years"
    assert policy.policy_type == PolicyType.ENDOWMENT
    assert policy.status == "In Force"
    assert policy.sum_assured == "300000"
    assert policy.premium_amount == "18659.00"
    assert policy.premium_due_date == "2027-01-15"
    assert policy.guaranteed_additions == "183000.0"
    assert policy.commencement_date == "2010-01-15"
    assert policy.maturity_date == "2030-01-15"
    assert policy.policy_term_years == 20
    assert policy.premium_payment_term_years == 20
    assert policy.premium_mode == "Yearly"


def test_detects_setus_tata_aia_policy_statement_layout():
    detect, _, _ = _policy_api()
    text = """
    Tata AIA Life
    Policy Statement Ref ****7777
    As on 30-Jun-2026
    Policy Type Sum Assured Fund/Surrender Value
    Tata AIA Fortune Pro (ULIP) ULIP - 950,000.00
    Tata AIA Sampoorna Raksha (Term) TERM 10,000,000.00 N/A (protection only)
    """
    assert detect(text) == "POLICY"


def test_term_policy_is_coverage_not_an_asset():
    _, Policy, value_policy = _policy_api()
    policy = Policy(
        policy_name="LIC New Tech-Term",
        policy_type=PolicyType.TERM,
        sum_assured="10000000",
        premium_amount="25000",
        currency="INR",
    )

    valuation = value_policy(policy)

    assert valuation.asset_value == Decimal("0")
    assert valuation.basis == "protection_only"
    assert valuation.requires_review is False


def test_endowment_uses_only_explicit_current_surrender_value():
    _, Policy, value_policy = _policy_api()
    policy = Policy(
        policy_name="LIC New Endowment Plan",
        policy_type=PolicyType.ENDOWMENT,
        sum_assured="1000000",
        surrender_value="245000",
        maturity_value="1400000",
        currency="INR",
    )

    valuation = value_policy(policy)

    assert valuation.asset_value == Decimal("245000")
    assert valuation.basis == "stated_surrender_value"
    assert valuation.requires_review is False


def test_endowment_without_surrender_value_fails_closed_for_review():
    _, Policy, value_policy = _policy_api()
    policy = Policy(
        policy_name="Traditional Savings Policy",
        policy_type=PolicyType.ENDOWMENT,
        sum_assured="1000000",
        premium_amount="60000",
        currency="INR",
    )

    valuation = value_policy(policy)

    assert valuation.asset_value is None
    assert valuation.requires_review is True
    assert "surrender" in valuation.reason.lower()


def test_ulip_uses_explicit_fund_value_and_never_recomputes_it():
    _, Policy, value_policy = _policy_api()
    policy = Policy(
        policy_name="Tata AIA Fortune Pro",
        policy_type=PolicyType.ULIP,
        fund_value="603703.26",
        units="12345.67",
        nav="999.99",  # Deliberately inconsistent: stated fund value must win.
        currency="INR",
    )

    valuation = value_policy(policy)

    assert valuation.asset_value == Decimal("603703.26")
    assert valuation.basis == "stated_fund_value"
    assert valuation.requires_review is False


def test_negative_policy_money_is_rejected():
    _, Policy, _ = _policy_api()

    try:
        Policy(
            policy_name="Invalid Policy",
            policy_type=PolicyType.ULIP,
            fund_value="-1",
            currency="INR",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("negative policy values must not pass validation")


def test_ingestion_agent_routes_real_synthetic_insurance_pdf_to_policy_schema(config):
    _, Policy, _ = _policy_api()

    class FakeLocalClient:
        def extract_structured(self, prompt, schema, system=None):
            assert schema is extraction.PolicyExtractionResult
            return schema(policies=[
                Policy(
                    policy_name="Tata AIA Fortune Pro (ULIP)",
                    policy_type=PolicyType.ULIP,
                    fund_value="950000",
                    currency="INR",
                ),
                Policy(
                    policy_name="Tata AIA Sampoorna Raksha (Term)",
                    policy_type=PolicyType.TERM,
                    sum_assured="10000000",
                    currency="INR",
                ),
            ])

    paths = generate_statements(config)
    policy_pdf = next(p for p in paths if p.stem == "tata_aia_life_insurance")
    result = IngestionAgent(config, client=FakeLocalClient()).run(str(policy_pdf))

    assert result.document_kind == "POLICY"
    assert result.holdings == []
    assert len(result.policies) == 2
    assert result.account_ref == "****7777"
    assert result.currency == "INR"
