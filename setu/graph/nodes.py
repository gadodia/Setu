"""Node functions — each wraps an agent/tool, takes State, returns a partial State update.

The nodes are deliberately thin: they translate between the serializable State (decimal strings,
ISO dates) and the agents/tools (Decimal, date), append trace events, and set the control fields the
edges route on. All financial computation lives in the agents/tools, never here and never in an LLM.

Nodes are constructed with their dependencies (config, local client, a Session factory) by
`build.py` via `make_nodes`, so they stay unit-testable with an in-memory DB and a fake model.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from setu.agents.ingestion_agent import IngestionAgent, IngestionResult
from setu.agents.reconciliation_agent import ReconciliationAgent
from setu.config import Config
from setu.db import statement_already_ingested
from setu.extraction import (
    ExtractedBalance,
    ExtractedHolding,
    ExtractedPolicy,
    policy_identity_issues,
    value_policy,
)
from setu.graph.state import SetuState, TraceEvent
from setu.models import (
    Account,
    AccountType,
    AssetClass,
    Balance,
    Geography,
    Holding,
    InsurancePolicy,
    Institution,
    Obligation,
    PolicyType,
    PolicyValue,
    Statement,
)

SessionFactory = Callable[[], Session]


def _ev(kind: str, node: str, content: str) -> TraceEvent:
    return TraceEvent(kind=kind, node=node, content=content)


def _holding_dicts(holdings: list[ExtractedHolding]) -> list[dict]:
    return [
        {
            "symbol": h.symbol,
            "name": h.name,
            "asset_class": h.asset_class.value,
            "geography": h.geography.value,
            "quantity": h.as_decimal("quantity").__str__(),
            "market_value": h.as_decimal("market_value").__str__(),
            "cost_basis": (
                None if h.cost_basis is None else h.as_decimal("cost_basis").__str__()
            ),
            "currency": h.currency.upper(),
        }
        for h in holdings
    ]


def _policy_dicts(policies: list[ExtractedPolicy]) -> list[dict]:
    return [policy.model_dump(mode="json", exclude_none=True) for policy in policies]


def _balance_dict(balance: ExtractedBalance | None) -> dict | None:
    return balance.model_dump(mode="json") if balance is not None else None


class Nodes:
    """Bundle of node callables sharing config, an IngestionAgent, and a Session factory."""

    def __init__(
        self,
        config: Config,
        session_factory: SessionFactory,
        ingestion_agent: IngestionAgent | None = None,
        reconciliation_agent: ReconciliationAgent | None = None,
    ):
        self.config = config
        self.session_factory = session_factory
        self.ingestion = ingestion_agent or IngestionAgent(config)
        self.reconciliation = reconciliation_agent or ReconciliationAgent(config)

    # --- ingest -----------------------------------------------------------------------------
    def ingest(self, state: SetuState) -> dict:
        path = state["statement_path"]
        trace = [_ev("thought", "ingest", f"Parsing and classifying financial document {path}.")]

        res: IngestionResult = self.ingestion.run(path)

        # Idempotency check (§2a): already in the ledger? Short-circuit downstream persistence.
        with self.session_factory() as session:
            already = statement_already_ingested(session, res.file_hash)

        trace.append(_ev(
            "observation", "ingest",
            f"{res.institution}: classified as {res.document_kind}; extracted "
            f"{len(res.holdings)} holding(s), {1 if res.balance else 0} balance(s), and "
            f"{len(res.policies)} policy record(s) in {res.currency}"
            + (" (already ingested)" if already else "."),
        ))
        return {
            "institution": res.institution,
            "account_ref": res.account_ref,
            "period_end": res.period_end.isoformat(),
            "currency": res.currency,
            "document_kind": res.document_kind,
            "policy_document_type": res.policy_document_type,
            "extracted": _holding_dicts(res.holdings),
            "extracted_policies": _policy_dicts(res.policies),
            "extracted_balance": _balance_dict(res.balance),
            "file_hash": res.file_hash,
            # Policy reconciliation uses only validated structured fields. A bank certificate
            # with an independent figure/words check does too. Avoid copying either document's
            # PII-heavy raw text into LangGraph's durable checkpoint when it is not needed.
            "raw_text": (
                res.raw_text
                if res.document_kind == "HOLDINGS"
                or (
                    res.document_kind == "BANK"
                    and (res.balance is None or res.balance.verification_amount is None)
                )
                else ""
            ),
            "already_ingested": already,
            "trace": trace,
        }

    # --- reconcile --------------------------------------------------------------------------
    def reconcile(self, state: SetuState) -> dict:
        if state.get("document_kind") == "POLICY":
            return self._reconcile_policies(state)
        if state.get("document_kind") == "BANK":
            return self._reconcile_bank(state)

        extracted = state.get("extracted", [])
        summed = sum((Decimal(h["market_value"]) for h in extracted), Decimal("0"))
        text = state.get("raw_text", "")

        # Guard: text unavailable but holdings were extracted. This is NOT "the document states
        # no total" — it means we can't run the independent check at all (e.g. a resume that lost
        # the text). Escalate to the human instead of silently treating it as reconciled.
        if not text.strip() and extracted:
            return {
                "stated_total": None,
                "sum_extracted": str(summed),
                "reconcile_delta": "0",
                "reconcile_status": "mismatch",
                "trace": [
                    _ev("thought", "reconcile",
                        f"Summed extracted value = {summed}, but statement text is unavailable — "
                        "cannot verify against a stated total."),
                    _ev("observation", "reconcile",
                        "No statement text to reconcile against → escalating for human review "
                        "rather than persisting unchecked."),
                ],
            }

        res = self.reconciliation.run(text, summed)

        stated = "none" if res.stated_total is None else f"{res.stated_total}"
        trace = [
            _ev("thought", "reconcile",
                f"Summed extracted value = {summed}; checking against the statement's stated total."),
            _ev("observation", "reconcile",
                f"stated={stated}, summed={summed}, delta={res.delta} → {res.status} "
                f"(tolerance {self.reconciliation.tolerance})."),
        ]
        return {
            "stated_total": None if res.stated_total is None else str(res.stated_total),
            "sum_extracted": str(summed),
            "reconcile_delta": str(res.delta),
            "reconcile_status": res.status,
            "trace": trace,
        }

    def _reconcile_bank(self, state: SetuState) -> dict:
        """Verify bank balances without allowing an account number to become the total."""
        balance = state.get("extracted_balance")
        if not balance:
            return {
                "stated_total": None,
                "sum_extracted": "0",
                "reconcile_delta": "0",
                "reconcile_status": "mismatch",
                "trace": [
                    _ev("thought", "reconcile", "Checking the document for one unambiguous bank balance."),
                    _ev(
                        "observation",
                        "reconcile",
                        "No labelled bank balance was extracted; human review is required.",
                    ),
                ],
            }

        amount = Decimal(balance["amount"])
        verification_raw = balance.get("verification_amount")
        if verification_raw is not None:
            stated = Decimal(verification_raw)
            delta = abs(stated - amount)
            is_words_check = balance.get("source_label") == "Balance in figures"
            if is_words_check:
                # A certificate's amount in figures and amount in words are two renderings of
                # the same legal value. Unlike a rounded portfolio total, they must match exactly.
                status = "ok" if delta == 0 else "mismatch"
                tolerance_description = "exact match required"
            else:
                denominator = abs(stated) if stated != 0 else Decimal("1")
                status = (
                    "ok"
                    if (delta / denominator) <= self.reconciliation.tolerance
                    else "mismatch"
                )
                tolerance_description = f"tolerance {self.reconciliation.tolerance}"
            return {
                "stated_total": str(stated),
                "sum_extracted": str(amount),
                "reconcile_delta": str(delta),
                "reconcile_status": status,
                "trace": [
                    _ev(
                        "thought",
                        "reconcile",
                        "Comparing the balance in figures with an independently parsed second "
                        "balance label or balance-in-words field.",
                    ),
                    _ev(
                        "observation",
                        "reconcile",
                        f"Independent bank-balance check produced {status} "
                        f"({tolerance_description}).",
                    ),
                ],
            }

        # Older/simple statements may expose only one balance field. Let the independent
        # reconciliation parser accept an explicit labelled balance, but never its weak
        # "largest figure" fallback: that fallback can be an account number on certificates.
        text = state.get("raw_text", "")
        res = self.reconciliation.run(text, amount)
        authoritative = any(hypothesis.authority < 2 for hypothesis in res.hypotheses)
        if not authoritative or res.stated_total is None:
            return {
                "stated_total": None,
                "sum_extracted": str(amount),
                "reconcile_delta": "0",
                "reconcile_status": "mismatch",
                "trace": [
                    _ev(
                        "thought",
                        "reconcile",
                        "Looking for an explicit balance label independent of the extracted value.",
                    ),
                    _ev(
                        "observation",
                        "reconcile",
                        "No independent labelled balance was available. Ignoring unlabelled large "
                        "numbers and escalating for human review.",
                    ),
                ],
            }

        return {
            "stated_total": str(res.stated_total),
            "sum_extracted": str(amount),
            "reconcile_delta": str(res.delta),
            "reconcile_status": res.status,
            "trace": [
                _ev(
                    "thought",
                    "reconcile",
                    "Checking the extracted bank balance against an explicit labelled amount.",
                ),
                _ev(
                    "observation",
                    "reconcile",
                    f"Independent labelled-balance check produced {res.status} "
                    f"(tolerance {self.reconciliation.tolerance}).",
                ),
            ],
        }

    def _reconcile_policies(self, state: SetuState) -> dict:
        valued: list[dict] = []
        reasons: list[str] = []
        warnings: list[str] = []
        total = Decimal("0")

        for raw in state.get("extracted_policies", []):
            policy = ExtractedPolicy.model_validate(raw)
            valuation = value_policy(policy)
            item = policy.model_dump(mode="json", exclude_none=True)
            item["asset_value"] = (
                None if valuation.asset_value is None else str(valuation.asset_value)
            )
            item["valuation_basis"] = valuation.basis
            item_warnings = policy_identity_issues(
                policy,
                state.get("policy_document_type", "UNKNOWN"),
            )
            if valuation.requires_review:
                item_warnings.append(f"{policy.policy_name}: {valuation.reason}")
            elif valuation.asset_value is not None:
                total += valuation.asset_value
            item["quality_issues"] = item_warnings
            warnings.extend(item_warnings)
            valued.append(item)

        if not valued:
            reasons.append("No policy records were extracted from the document.")

        review_reason = " ".join(reasons) or None
        status = "mismatch" if review_reason else "ok"
        observation = (
            f"Verified current policy values total {total}; partial contracts without a stated "
            "surrender/fund value remain unknown and excluded from net worth."
            if status == "ok"
            else f"Policy valuation requires review: {review_reason}"
        )
        return {
            "extracted_policies": valued,
            "stated_total": None,
            "sum_extracted": str(total),
            "reconcile_delta": "0",
            "reconcile_status": status,
            "policy_review_reason": review_reason,
            "policy_warnings": warnings,
            "trace": [
                _ev("thought", "reconcile", "Applying deterministic insurance valuation rules."),
                _ev("observation", "reconcile", observation),
            ],
        }

    # --- ask_user (human-in-the-loop; interrupt happens here) -------------------------------
    def ask_user(self, state: SetuState) -> dict:
        # Import here so the module imports cleanly even if langgraph isn't installed (tests of
        # agents/tools in isolation don't need it).
        from langgraph.types import interrupt

        if state.get("document_kind") == "POLICY" and state.get("policy_review_reason"):
            question = (
                f"Policy review required for {state.get('institution', 'this document')}: "
                f"{state['policy_review_reason']} No recognizable policy contract can be "
                "persisted from this extraction. Reject this extraction. [reject]"
            )
        else:
            question = (
                f"Reconciliation mismatch for {state.get('institution', 'this statement')}: "
                f"extracted total {state.get('sum_extracted')} vs stated {state.get('stated_total')} "
                f"(delta {state.get('reconcile_delta')}). Accept the extraction anyway? [accept/reject]"
            )
        # interrupt() pauses+persists the run and returns the resume value on continuation.
        decision = interrupt({"question": question, "state_summary": {
            "institution": state.get("institution"),
            "sum_extracted": state.get("sum_extracted"),
            "stated_total": state.get("stated_total"),
        }})
        decision = str(decision).strip().lower()
        return {
            "pending_question": question,
            "user_decision": decision,
            "trace": [_ev("ask_user", "ask_user", f"Human decision: {decision}")],
        }

    # --- persist ----------------------------------------------------------------------------
    def persist(self, state: SetuState) -> dict:
        # Fail closed on rejection or invalid decisions. Missing optional valuation evidence is
        # retained on a partial policy contract and never represented as a known zero value.
        decision = state.get("user_decision")
        invalid_decision = decision not in (None, "accept", "reject")
        if decision == "reject" or invalid_decision:
            reason = (
                "User rejected or supplied an invalid decision — nothing written to ledger."
            )
            return {
                "persisted_holdings": 0,
                "persisted_balances": 0,
                "persisted_policies": 0,
                "persisted_obligations": 0,
                "persisted_skipped": False,
                "trace": [_ev("observation", "persist", reason)],
            }

        if state.get("already_ingested"):
            return {
                "persisted_holdings": 0,
                "persisted_balances": 0,
                "persisted_policies": 0,
                "persisted_obligations": 0,
                "persisted_skipped": True,
                "trace": [_ev("observation", "persist",
                              "Statement already in ledger (idempotent skip).")],
            }

        from datetime import date

        extracted = state.get("extracted", [])
        balance = state.get("extracted_balance")
        policies = state.get("extracted_policies", [])
        period_end = date.fromisoformat(state["period_end"])
        n_holdings = 0
        n_balances = 0
        n_policies = 0
        n_obligations = 0
        with self.session_factory() as session:
            stmt = Statement(
                institution=state.get("institution", "Unknown"),
                account_ref=state.get("account_ref"),
                file_name=state.get("source_name") or state.get("statement_path", "").split("/")[-1],
                file_hash=state["file_hash"],
                period_end=period_end,
            )
            session.add(stmt)

            institution_name = state.get("institution", "Unknown")
            geography = _geo_of(extracted, policies, balance)
            inst = session.scalar(select(Institution).where(
                Institution.name == institution_name,
                Institution.geography == geography,
            ))
            if inst is None:
                inst = Institution(name=institution_name, geography=geography)
                session.add(inst)
                session.flush()

            if state.get("document_kind") == "POLICY":
                account_type = AccountType.INSURANCE
            elif state.get("document_kind") == "BANK":
                account_type = AccountType.BANK
            else:
                account_type = AccountType.BROKERAGE
            account = session.scalar(select(Account).where(
                Account.institution_id == inst.id,
                Account.account_ref == state.get("account_ref"),
                Account.currency == state.get("currency", "USD"),
            ))
            if account is None:
                account = Account(
                    institution=inst,
                    name=institution_name,
                    account_type=account_type,
                    currency=state.get("currency", "USD"),
                    account_ref=state.get("account_ref"),
                )
                session.add(account)
            session.flush()  # assign stmt.id / account.id

            for h in extracted:
                session.add(Holding(
                    account_id=account.id,
                    statement_id=stmt.id,
                    symbol=h.get("symbol"),
                    name=h.get("name", ""),
                    asset_class=AssetClass(h["asset_class"]),
                    geography=Geography(h["geography"]),
                    quantity=Decimal(h.get("quantity", "0")),
                    market_value=Decimal(h["market_value"]),
                    cost_basis=(
                        None if h.get("cost_basis") is None else Decimal(h["cost_basis"])
                    ),
                    currency=h.get("currency", "USD"),
                    as_of_date=period_end,
                ))
                n_holdings += 1

            if balance is not None:
                session.add(Balance(
                    account_id=account.id,
                    statement_id=stmt.id,
                    amount=Decimal(balance["amount"]),
                    currency=balance.get("currency", state.get("currency", "USD")),
                    as_of_date=period_end,
                ))
                n_balances = 1

            for policy in policies:
                asset_value = policy.get("asset_value")
                quality_issues = policy.get("quality_issues", [])
                if policy["policy_type"] == PolicyType.TERM.value:
                    current_value_status = "not_provided" if quality_issues else "not_applicable"
                elif asset_value is None:
                    current_value_status = "not_provided"
                else:
                    current_value_status = "verified"
                session.add(InsurancePolicy(
                    account_id=account.id,
                    statement_id=stmt.id,
                    policy_name=policy["policy_name"],
                    policy_type=PolicyType(policy["policy_type"]),
                    plan_number=policy.get("plan_number"),
                    status=policy.get("status"),
                    sum_assured=(
                        None if policy.get("sum_assured") is None
                        else Decimal(policy["sum_assured"])
                    ),
                    currency=policy.get("currency", state.get("currency", "INR")),
                    commencement_date=_optional_iso_date(policy.get("commencement_date")),
                    maturity_date=_optional_iso_date(policy.get("maturity_date")),
                    policy_term_years=policy.get("policy_term_years"),
                    premium_payment_term_years=policy.get("premium_payment_term_years"),
                    premium_amount=(
                        None if policy.get("premium_amount") is None
                        else Decimal(policy["premium_amount"])
                    ),
                    premium_due_date=_optional_iso_date(policy.get("premium_due_date")),
                    premium_mode=policy.get("premium_mode"),
                    vested_bonus=_optional_decimal(policy.get("vested_bonus")),
                    guaranteed_additions=_optional_decimal(policy.get("guaranteed_additions")),
                    stated_maturity_value=_optional_decimal(policy.get("maturity_value")),
                    maturity_benefit_4pct=_optional_decimal(policy.get("maturity_benefit_4pct")),
                    maturity_benefit_8pct=_optional_decimal(policy.get("maturity_benefit_8pct")),
                    document_type=state.get("policy_document_type", "UNKNOWN"),
                    evidence_status="partial" if quality_issues else "complete",
                    current_value_status=current_value_status,
                ))
                n_policies += 1

                if asset_value is not None and policy["policy_type"] != PolicyType.TERM.value:
                    session.add(PolicyValue(
                        account_id=account.id,
                        statement_id=stmt.id,
                        policy_name=policy["policy_name"],
                        policy_type=PolicyType(policy["policy_type"]),
                        sum_assured=(
                            None if policy.get("sum_assured") is None
                            else Decimal(policy["sum_assured"])
                        ),
                        asset_value=Decimal(asset_value),
                        currency=policy.get("currency", state.get("currency", "INR")),
                        as_of_date=period_end,
                    ))

                premium = policy.get("premium_amount")
                if premium is not None and Decimal(premium) > 0:
                    due_date = _optional_iso_date(policy.get("premium_due_date"))
                    session.add(Obligation(
                        account_id=account.id,
                        statement_id=stmt.id,
                        description=f"Premium: {policy['policy_name']}",
                        amount=Decimal(premium),
                        currency=policy.get("currency", state.get("currency", "INR")),
                        due_date=due_date,
                        recurring=True,
                    ))
                    n_obligations += 1
            session.commit()

        return {
            "persisted_holdings": n_holdings,
            "persisted_balances": n_balances,
            "persisted_policies": n_policies,
            "persisted_obligations": n_obligations,
            "persisted_skipped": False,
            "trace": [_ev(
                "action",
                "persist",
                f"Wrote {n_holdings} holding(s), {n_balances} balance(s), "
                f"{n_policies} policy contract(s), "
                f"{n_obligations} obligation(s), and the statement to the ledger.",
            )],
        }


def _geo_of(
    extracted: list[dict],
    policies: list[dict] | None = None,
    balance: dict | None = None,
) -> Geography:
    """Account geography = the geography of its holdings (India if any INR/INDIA present)."""
    for h in extracted:
        if h.get("geography") == Geography.INDIA.value:
            return Geography.INDIA
    if any(p.get("currency", "").upper() == "INR" for p in (policies or [])):
        return Geography.INDIA
    if balance and balance.get("currency", "").upper() == "INR":
        return Geography.INDIA
    return Geography.US


def _optional_iso_date(value: str | None):
    if not value:
        return None
    from datetime import date, datetime

    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _optional_decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)
