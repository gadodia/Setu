"""LLM-based holding extraction — statement text → structured, validated holdings.

The PII-heavy step runs on the LOCAL model (Ollama) so raw statement text never leaves the
machine. Output is constrained to a pydantic schema (Ollama structured outputs), then validated
here. The model classifies and transcribes; it does NOT compute — market values are read from the
statement as-is, and reconciliation (Week 4) later verifies them against the stated total.
"""

from __future__ import annotations

import ast
import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from setu.config import Config, load_config
from setu.llm.local import LocalClient
from setu.models import AssetClass, Geography, PolicyType
from setu.tools.pdf_extract import extract as pdf_extract

# Small local models sometimes emit a money value as a nested object
# ({"amount": 60000.0, "currency": "USD"}) or its Python-repr string
# ("{u'amount': 60000.0, ...}") instead of a bare number. Pull the amount out.
_AMOUNT_KEY_RE = re.compile(r"['\"]?amount['\"]?\s*:\s*([0-9][0-9,]*\.?[0-9]*)")


def _to_number_string(v: object) -> str:
    """Coerce a model-emitted value to a bare decimal string.

    Accepts numbers, plain strings ("$60,000.00"), a {amount, currency} dict, or the
    stringified repr of such a dict. Strips currency symbols and thousands separators.
    """
    if isinstance(v, dict):
        v = v.get("amount", v.get("value", "0"))
    elif isinstance(v, str) and "amount" in v:
        # Stringified dict-repr, e.g. "{u'amount': 60000.0, u'currency': u'USD'}".
        try:
            parsed = ast.literal_eval(v.replace("u'", "'").replace('u"', '"'))
            if isinstance(parsed, dict):
                v = parsed.get("amount", parsed.get("value", "0"))
        except (ValueError, SyntaxError):
            m = _AMOUNT_KEY_RE.search(v)
            if m:
                v = m.group(1)
    return str(v).replace(",", "").replace("$", "").replace("₹", "").strip() or "0"


class ExtractedHolding(BaseModel):
    symbol: str | None = Field(default=None, description="Ticker/symbol if present, else null.")
    name: str = Field(description="Security or fund name as printed.")
    asset_class: AssetClass = Field(description="EQUITY, DEBT, CASH, INSURANCE_CASH_VALUE, or REAL_ASSET.")
    geography: Geography = Field(description="US or INDIA.")
    quantity: str = Field(default="0", description="Units/shares as a plain decimal number string, e.g. \"120.5\".")
    market_value: str = Field(
        description="Market value as a PLAIN decimal number string only, e.g. \"60000.00\" "
        "(no currency symbol, no object, no commas). Put the currency in the separate `currency` field."
    )
    cost_basis: str | None = Field(
        default=None,
        description="Total cost basis or invested amount only when explicitly printed.",
    )
    currency: str = Field(description="ISO currency code, e.g. USD or INR.")

    @field_validator("market_value", "quantity", mode="before")
    @classmethod
    def _coerce_decimal(cls, v: object) -> str:
        s = _to_number_string(v)
        try:
            Decimal(s)
        except InvalidOperation as e:
            raise ValueError(f"not a valid number: {v!r}") from e
        return s

    @field_validator("cost_basis", mode="before")
    @classmethod
    def _coerce_optional_cost_basis(cls, v: object) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        s = _to_number_string(v)
        try:
            value = Decimal(s)
        except InvalidOperation as e:
            raise ValueError(f"not a valid cost basis: {v!r}") from e
        if value < 0:
            raise ValueError("cost basis cannot be negative")
        return s

    def as_decimal(self, field: str) -> Decimal:
        return Decimal(_to_number_string(getattr(self, field)))


class ExtractionResult(BaseModel):
    holdings: list[ExtractedHolding] = Field(default_factory=list)


class ExtractedBalance(BaseModel):
    """A bank balance copied from an explicitly labelled statement field."""

    amount: str = Field(description="Closing/current balance as a plain decimal string.")
    currency: str = Field(description="ISO currency code, e.g. USD or INR.")
    source_label: str = Field(description="The statement label used for the amount.")
    verification_amount: str | None = Field(
        default=None,
        description="Independent amount read from a second label or the balance-in-words column.",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_decimal(cls, v: object) -> str:
        s = _to_number_string(v)
        try:
            Decimal(s)
        except InvalidOperation as e:
            raise ValueError(f"not a valid balance: {v!r}") from e
        return s

    @field_validator("verification_amount", mode="before")
    @classmethod
    def _coerce_optional_decimal(cls, v: object) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        s = _to_number_string(v)
        try:
            Decimal(s)
        except InvalidOperation as e:
            raise ValueError(f"not a valid verification balance: {v!r}") from e
        return s

    def as_decimal(self) -> Decimal:
        return Decimal(self.amount)


DocumentKind = Literal["HOLDINGS", "POLICY", "BANK"]
PolicyDocumentType = Literal[
    "POLICY_STATEMENT",
    "PREMIUM_NOTICE",
    "PREMIUM_RECEIPT",
    "UNKNOWN",
]


class ExtractedPolicy(BaseModel):
    """Fields transcribed from an insurance document; no values are inferred here."""

    policy_name: str = Field(description="Policy or product name as printed.")
    policy_type: PolicyType = Field(description="TERM, ENDOWMENT, or ULIP.")
    policy_number: str | None = Field(
        default=None,
        description="Masked policy identifier, kept separate from the product plan number.",
    )
    plan_number: str | None = Field(default=None, description="LIC plan number or product code, if printed.")
    status: str | None = Field(default=None, description="Policy status as printed, if present.")
    sum_assured: str | None = Field(default=None, description="Coverage amount as printed.")
    surrender_value: str | None = Field(default=None, description="Current surrender value, only if explicit.")
    fund_value: str | None = Field(default=None, description="Current ULIP fund value, only if explicit.")
    maturity_value: str | None = Field(default=None, description="Future maturity value, only if explicit.")
    premium_amount: str | None = Field(default=None, description="Premium amount as printed.")
    premium_due_date: str | None = Field(default=None, description="Due date as printed, ideally YYYY-MM-DD.")
    commencement_date: str | None = Field(default=None, description="Policy commencement date, ideally YYYY-MM-DD.")
    maturity_date: str | None = Field(default=None, description="Policy maturity date, ideally YYYY-MM-DD.")
    policy_term_years: int | None = Field(default=None, ge=1, le=100)
    premium_payment_term_years: int | None = Field(default=None, ge=1, le=100)
    premium_mode: str | None = Field(default=None, description="Monthly, quarterly, half-yearly, yearly, or single.")
    vested_bonus: str | None = Field(default=None, description="Bonus already vested, only if explicitly printed.")
    guaranteed_additions: str | None = Field(default=None, description="Guaranteed additions already stated.")
    maturity_benefit_4pct: str | None = Field(default=None, description="Official benefit illustration maturity amount at 4%, if printed.")
    maturity_benefit_8pct: str | None = Field(default=None, description="Official benefit illustration maturity amount at 8%, if printed.")
    units: str | None = Field(default=None, description="ULIP units as printed.")
    nav: str | None = Field(default=None, description="ULIP NAV as printed.")
    currency: str = Field(default="INR", description="ISO currency code.")

    @field_validator(
        "sum_assured",
        "surrender_value",
        "fund_value",
        "maturity_value",
        "premium_amount",
        "units",
        "nav",
        "vested_bonus",
        "guaranteed_additions",
        "maturity_benefit_4pct",
        "maturity_benefit_8pct",
        mode="before",
    )
    @classmethod
    def _coerce_optional_decimal(cls, v: object) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        s = _to_number_string(v)
        try:
            value = Decimal(s)
        except InvalidOperation as e:
            raise ValueError(f"not a valid number: {v!r}") from e
        if value < 0:
            raise ValueError("policy monetary and unit values cannot be negative")
        return s

    def as_decimal(self, field: str) -> Decimal | None:
        value = getattr(self, field)
        return Decimal(value) if value is not None else None


class PolicyExtractionResult(BaseModel):
    policies: list[ExtractedPolicy] = Field(default_factory=list)


class PolicyValuation(BaseModel):
    """A deterministic interpretation of a transcribed policy value."""

    asset_value: Decimal | None
    basis: str
    requires_review: bool = False
    reason: str = ""


_POLICY_MARKERS = (
    "policy number",
    "policy no",
    "policy ref",
    "life assured",
    "sum assured",
    "surrender value",
    "premium due",
    "premium amount",
    "fund value",
    "maturity benefit",
)


def detect_document_kind(statement_text: str) -> DocumentKind:
    """Route policy, bank-balance, and investment statements conservatively."""
    normalized = " ".join(statement_text.lower().split())
    marker_count = sum(marker in normalized for marker in _POLICY_MARKERS)
    insurance_context = any(
        marker in normalized
        for marker in (
            "life insurance",
            "insurance policy",
            "policy statement",
            "life assured",
            "lic of india",
        )
    )
    if marker_count >= 2 and insurance_context:
        return "POLICY"

    balance_context = any(
        marker in normalized
        for marker in ("bank", "savings account", "current account", "checking account")
    )
    balance_label = any(
        marker in normalized
        for marker in ("closing balance", "ending balance", "available balance")
    )
    compact = re.sub(r"[^a-z]", "", normalized)
    balance_certificate = (
        "balanceconfirmationcertificate" in compact
        or (
            "balanceinfigures" in compact
            and "typeofaccounts" in compact
            and "accountnumber" in compact
        )
    )
    return "BANK" if (balance_context and balance_label) or balance_certificate else "HOLDINGS"


_BALANCE_NUM = r"[-+]?[0-9][0-9,]*(?:\.[0-9]+)?"


def extract_balance(
    statement_text: str,
    tables: list[list[list[str | None]]] | None = None,
) -> ExtractedBalance | None:
    """Copy a labelled bank balance without involving an LLM.

    Closing/ending balance is preferred over available balance. The latter remains a fallback for
    institutions that print only one usable balance field.
    """
    table_balance = _extract_balance_certificate_table(statement_text, tables or [])
    if table_balance is not None:
        return table_balance

    patterns = (
        ("Closing Balance", r"Closing\s+Balance"),
        ("Ending Balance", r"Ending\s+Balance"),
        ("Current Balance", r"Current\s+Balance"),
        ("Available Balance", r"Available\s+Balance"),
    )
    labelled: list[tuple[str, str]] = []
    for source_label, label_pattern in patterns:
        match = re.search(
            rf"\b{label_pattern}\b\s*:?\s*(?:Rs\.?|INR|USD|\$|₹)?\s*({_BALANCE_NUM})",
            statement_text,
            re.IGNORECASE,
        )
        if match:
            labelled.append((source_label, match.group(1)))
    if labelled:
        source_label, amount = labelled[0]
        verification = labelled[1][1] if len(labelled) > 1 else None
        return ExtractedBalance(
            amount=amount,
            currency=_balance_currency(statement_text),
            source_label=source_label,
            verification_amount=verification,
        )
    return None


def _extract_balance_certificate_table(
    statement_text: str,
    tables: list[list[list[str | None]]],
) -> ExtractedBalance | None:
    """Read the explicit Balance-in-figures column from bank balance certificates."""
    for table in tables:
        if len(table) < 2:
            continue
        header = table[0]
        balance_index = next(
            (
                index
                for index, cell in enumerate(header)
                if "balanceinfigures" in re.sub(r"[^a-z]", "", (cell or "").lower())
            ),
            None,
        )
        if balance_index is None:
            continue
        words_index = next(
            (
                index
                for index, cell in enumerate(header)
                if "balanceinwords" in re.sub(r"[^a-z]", "", (cell or "").lower())
            ),
            None,
        )
        parsed: list[ExtractedBalance] = []
        for row in table[1:]:
            if balance_index >= len(row):
                continue
            figure_cell = row[balance_index] or ""
            amount = _balance_figure(figure_cell)
            if amount is None:
                continue
            words_amount = (
                _balance_words(row[words_index] or "")
                if words_index is not None and words_index < len(row)
                else None
            )
            parsed.append(ExtractedBalance(
                amount=str(amount),
                currency=_balance_currency(f"{figure_cell} {statement_text}"),
                source_label="Balance in figures",
                verification_amount=None if words_amount is None else str(words_amount),
            ))
        # A certificate containing multiple accounts needs a list-valued ingestion design. Do not
        # silently choose one or sum them under a single account.
        if len(parsed) == 1:
            return parsed[0]
    return None


def _balance_currency(text: str) -> str:
    return (
        "INR"
        if re.search(r"(?:\bINR\b|Rs\.?|₹)", text, re.IGNORECASE)
        else "USD"
    )


def _balance_figure(cell: str) -> Decimal | None:
    match = re.search(
        rf"(?:(?:INR|USD|Rs\.?|\$|₹)\s*)+({_BALANCE_NUM})",
        cell,
        re.IGNORECASE,
    )
    if match is None:
        match = re.search(rf"({_BALANCE_NUM})", cell)
    if match is None:
        return None
    value = _to_decimal_text(match.group(1))
    if value is not None and "debit" in cell.lower() and value > 0:
        value = -value
    return value


def _to_decimal_text(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").strip())
    except InvalidOperation:
        return None


_SMALL_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUMBER_SCALES = {
    "thousand": 1_000,
    "lakh": 100_000,
    "lac": 100_000,
    "crore": 10_000_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
}
_NUMBER_WORD_PATTERN = re.compile(
    "|".join(sorted(
        (*_SMALL_NUMBER_WORDS, "hundred", *_NUMBER_SCALES),
        key=len,
        reverse=True,
    )),
    re.IGNORECASE,
)


def _balance_words(cell: str) -> Decimal | None:
    """Parse concatenated Indian/English amount words as an independent certificate check."""
    is_debit = "debit" in cell.lower()
    compact = re.sub(r"[^a-z]", "", cell.lower())
    for noise in ("creditbalance", "debitbalance", "rupees", "rupee", "inr", "only"):
        compact = compact.replace(noise, "")
    paise_words = ""
    if "paise" in compact:
        before_paise, after_paise = compact.split("paise", 1)
        # HDFC certificates can print either "... and Twelve Paise" or
        # "... and Paise Twelve". Prefer a valid minor-unit number after the word Paise.
        after_value = _number_words_value(after_paise)
        if after_value is not None and 0 <= after_value <= 99:
            compact = before_paise
            paise_words = after_paise
        else:
            compact = before_paise
            # Search from the right for an "and" whose suffix is a valid 0-99 amount. Merely
            # using rfind() is unsafe because the letters "and" also end the word "thousand".
            for separator in reversed([m.start() for m in re.finditer("and", before_paise)]):
                candidate = before_paise[separator + 3:]
                candidate_value = _number_words_value(candidate)
                if candidate and candidate_value is not None and 0 <= candidate_value <= 99:
                    compact = before_paise[:separator]
                    paise_words = candidate
                    break
    whole = _number_words_value(compact)
    if whole is None:
        return None
    paise = _number_words_value(paise_words) if paise_words else 0
    if paise is None or paise < 0 or paise > 99:
        return None
    value = Decimal(whole) + (Decimal(paise) / Decimal("100"))
    return -value if is_debit else value


def _number_words_value(compact: str) -> int | None:
    tokens = [match.group(0).lower() for match in _NUMBER_WORD_PATTERN.finditer(compact)]
    if not tokens:
        return None
    total = 0
    current = 0
    for token in tokens:
        if token in _SMALL_NUMBER_WORDS:
            current += _SMALL_NUMBER_WORDS[token]
        elif token == "hundred":
            current = max(current, 1) * 100
        else:
            total += max(current, 1) * _NUMBER_SCALES[token]
            current = 0
    return total + current


def detect_policy_document_type(statement_text: str) -> PolicyDocumentType:
    """Distinguish valuation-bearing policy documents from premium-only evidence."""
    normalized = " ".join(statement_text.lower().split())
    if any(marker in normalized for marker in (
        "premium receipt",
        "renewal premium receipt",
        "payment receipt",
        "premium payment acknowledgement",
    )):
        return "PREMIUM_RECEIPT"
    if any(marker in normalized for marker in (
        "renewal premium notice",
        "premium notice",
        "renewal premium due",
        "premium due notice",
    )):
        return "PREMIUM_NOTICE"
    if any(marker in normalized for marker in (
        "policy statement",
        "policy status report",
        "policy schedule",
        "policy document",
        "benefit illustration",
        "unit statement",
    )):
        return "POLICY_STATEMENT"
    return "UNKNOWN"


_GENERIC_POLICY_NAMES = {
    "term",
    "ulip",
    "endowment",
    "policy",
    "insurance",
    "insurance policy",
    "life insurance",
    "plan",
    "unknown",
    "unknown policy",
}


def policy_identity_issues(
    policy: ExtractedPolicy,
    document_type: PolicyDocumentType = "UNKNOWN",
) -> list[str]:
    """Return reasons a policy record is not safe to persist without better evidence."""
    issues: list[str] = []
    if document_type in {"PREMIUM_NOTICE", "PREMIUM_RECEIPT"}:
        issues.append(
            "This is a premium notice or receipt, not a complete policy statement."
        )
    normalized_name = " ".join(policy.policy_name.lower().split()).strip(" .:-")
    if normalized_name in _GENERIC_POLICY_NAMES or len(normalized_name) < 4:
        issues.append("A specific policy or product name was not extracted.")
    if policy.policy_type in {PolicyType.TERM, PolicyType.ENDOWMENT} and policy.sum_assured is None:
        issues.append("No explicit sum assured was extracted, so coverage cannot be verified.")
    return issues


def value_policy(policy: ExtractedPolicy) -> PolicyValuation:
    """Choose the current asset value without estimating from premiums or coverage."""
    if policy.policy_type == PolicyType.TERM:
        return PolicyValuation(asset_value=Decimal("0"), basis="protection_only")

    if policy.policy_type == PolicyType.ENDOWMENT:
        value = policy.as_decimal("surrender_value")
        if value is None:
            return PolicyValuation(
                asset_value=None,
                basis="missing_current_value",
                requires_review=True,
                reason="No explicit current surrender value was found.",
            )
        return PolicyValuation(asset_value=value, basis="stated_surrender_value")

    if policy.policy_type == PolicyType.ULIP:
        value = policy.as_decimal("fund_value")
        if value is None:
            return PolicyValuation(
                asset_value=None,
                basis="missing_current_value",
                requires_review=True,
                reason="No explicit current fund value was found.",
            )
        return PolicyValuation(asset_value=value, basis="stated_fund_value")

    return PolicyValuation(
        asset_value=None,
        basis="unsupported_policy_type",
        requires_review=True,
        reason=f"Unsupported policy type: {policy.policy_type}",
    )


_SYSTEM = (
    "You extract investment holdings from a financial statement's raw text. "
    "Transcribe values EXACTLY as printed — do not compute, round, or invent anything. "
    "Classify each row's asset_class and geography. If a value is absent, omit the holding. "
    "Return only holdings that are securities/funds (not cash balances or insurance policies). "
    "Copy `cost_basis` only when the same row explicitly prints total cost basis, total cost, "
    "book value, or invested amount. Otherwise return null; never derive it from quantity or NAV. "
    "IMPORTANT: `market_value` and `quantity` must each be a PLAIN number as a string "
    '(e.g. "60000.00") — never an object, never with a currency symbol or commas. '
    "`cost_basis` follows the same plain-number rule. The currency code goes only in the separate "
    "`currency` field."
)


_POLICY_SYSTEM = (
    "You transcribe insurance-policy fields from raw document text. "
    "Never calculate, estimate, or infer a monetary value. Use null when a field is absent. "
    "Classify pure protection as TERM, unit-linked products as ULIP, and traditional savings, "
    "money-back, or endowment products as ENDOWMENT. A document may contain multiple policies. "
    "Do not treat sum assured, maturity benefit, bonuses, or premiums as current asset value. "
    "Use surrender_value only when the document explicitly labels a current surrender value, "
    "and fund_value only when it explicitly labels the current ULIP fund value. "
    "The policy_name must be the specific printed product or plan name, never merely TERM, ULIP, "
    "ENDOWMENT, policy, or plan. Use 'Unknown policy' when no product name is printed. "
    "Keep the policy number separate from the plan number; never put a policy identifier in the "
    "plan_number field. Also transcribe plan number, commencement and maturity dates, policy term, premium payment "
    "term, premium mode, vested bonus, guaranteed additions, and official 4%/8% benefit "
    "illustration maturity amounts when they are explicitly printed. Do not derive them. "
    "All numeric fields must be plain decimal strings without symbols or commas."
)


def extract_holdings(
    statement_text: str,
    client: LocalClient | None = None,
    config: Config | None = None,
) -> ExtractionResult:
    """Run the local model over statement text to produce validated structured holdings."""
    config = config or load_config()
    client = client or LocalClient(config)

    prompt = (
        "Extract every investment holding from this statement text as JSON matching the schema.\n\n"
        f"--- STATEMENT TEXT ---\n{statement_text}\n--- END ---"
    )
    model_result = client.extract_structured(prompt, ExtractionResult, system=_SYSTEM)
    return reconcile_holding_cost_basis(statement_text, model_result)


def reconcile_holding_cost_basis(
    statement_text: str,
    model_result: ExtractionResult,
) -> ExtractionResult:
    """Overlay explicit row-level cost basis when a small local model omits it.

    The parser is intentionally narrow: it activates only when a recognized cost header is
    printed and pairs cost with a holding by the row's already-extracted market value. If there is
    no explicit cost evidence, any model-supplied cost is cleared so ROI remains unknown.
    """
    normalized = " ".join(statement_text.lower().split())
    has_cost_header = any(
        label in normalized
        for label in ("cost basis", "invested amount", "book value", "total cost")
    )
    if not has_cost_header:
        return ExtractionResult(holdings=[
            ExtractedHolding.model_validate({**holding.model_dump(), "cost_basis": None})
            for holding in model_result.holdings
        ])

    candidates: dict[Decimal, list[Decimal]] = {}
    number = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
    for line in statement_text.splitlines():
        # US rows end in: quantity, $cost basis, $market value.
        brokerage = re.search(
            rf"{number}\s+\$\s*{number}\s+\$\s*{number}\s*$",
            line,
        )
        if brokerage:
            cost = Decimal(brokerage.group(2).replace(",", ""))
            current = Decimal(brokerage.group(3).replace(",", ""))
            candidates.setdefault(current, []).append(cost)
            continue

        # CAS rows end in: units, invested amount, NAV, current value.
        cas = re.search(rf"{number}\s+{number}\s+{number}\s+{number}\s*$", line)
        if cas and "invested amount" in normalized:
            cost = Decimal(cas.group(2).replace(",", ""))
            current = Decimal(cas.group(4).replace(",", ""))
            candidates.setdefault(current, []).append(cost)

    reconciled: list[ExtractedHolding] = []
    for holding in model_result.holdings:
        values = holding.model_dump()
        matches = candidates.get(holding.as_decimal("market_value"), [])
        if len(matches) == 1:
            values["cost_basis"] = str(matches[0])
        reconciled.append(ExtractedHolding.model_validate(values))
    return ExtractionResult(holdings=reconciled)


def extract_policies(
    statement_text: str,
    client: LocalClient | None = None,
    config: Config | None = None,
) -> PolicyExtractionResult:
    """Use the local model to transcribe policy fields into a validated schema."""
    config = config or load_config()
    client = client or LocalClient(config)
    prompt = (
        "Transcribe every insurance policy in this document as JSON matching the schema.\n\n"
        f"--- POLICY DOCUMENT ---\n{statement_text}\n--- END ---"
    )
    model_result = client.extract_structured(prompt, PolicyExtractionResult, system=_POLICY_SYSTEM)
    return reconcile_policy_labels(statement_text, model_result)


def reconcile_policy_labels(
    statement_text: str,
    model_result: PolicyExtractionResult,
) -> PolicyExtractionResult:
    """Overlay exact, visibly labelled fields on the local model's interpretation.

    Small local models are useful for classifying unfamiliar policy language, but they can omit
    obvious values. Label extraction is deterministic and therefore authoritative for fields such
    as ``Sum Assured`` and ``Instalment Premium``. Raw policy identifiers are masked before they
    enter graph state or the ledger.
    """
    labelled = _extract_policy_labels(statement_text)
    if not model_result.policies:
        return model_result

    policies: list[ExtractedPolicy] = []
    for model_policy in model_result.policies:
        values = model_policy.model_dump()
        for field, value in labelled.items():
            if value is not None:
                values[field] = value
        values["policy_number"] = _mask_identifier(values.get("policy_number"))
        policy_number = labelled.get("policy_number")
        if policy_number and _same_identifier(model_policy.plan_number, policy_number):
            values["plan_number"] = None
        policies.append(ExtractedPolicy.model_validate(values))
    return PolicyExtractionResult(policies=policies)


def _extract_policy_labels(text: str) -> dict[str, object]:
    """Extract common LIC status/schedule labels without interpreting policy economics."""
    one_line = " ".join(text.split())
    policy_number = _label_text(one_line, r"Policy\s+(?:Number|No\.?)", r"[A-Za-z0-9/-]+")
    policy_name = _label_text(
        one_line,
        r"Plan\s+Name",
        r".+?",
        stop=r"\s+Policy\s+Status\s*:",
    )
    status = _label_text(
        one_line,
        r"Policy\s+Status",
        r".+?",
        stop=r"\s+(?:Instalment\s+Premium|Sum\s+Assured|Premium\s+due)\s*:",
    )
    # pdfplumber can place a wrapped "Years" token after the adjacent status column.
    if policy_name and re.search(r"\b\d+$", policy_name) and status and status.endswith(" Years"):
        policy_name = f"{policy_name} Years"
        status = status.removesuffix(" Years").strip()
    return {
        "policy_name": policy_name,
        "policy_type": _policy_type_from_name(policy_name),
        "policy_number": _mask_identifier(policy_number),
        "status": status,
        "plan_number": _label_text(one_line, r"(?:Plan|Table)\s+(?:Number|No\.?)", r"\d+"),
        "sum_assured": _label_money(one_line, r"(?:Basic\s+)?Sum\s+Assured"),
        "premium_amount": _first_not_none(
            _label_money(one_line, r"Instalment\s+Premium"),
            _label_money(one_line, r"Renewal\s+Premium"),
            _label_money(one_line, r"Premium\s+Amount"),
        ),
        "premium_due_date": _label_date(one_line, r"Premium\s+due\s+from"),
        "commencement_date": _label_date(one_line, r"Commencement\s+Date"),
        "maturity_date": _label_date(one_line, r"Date\s+of\s+Maturity"),
        "policy_term_years": _label_int(one_line, r"Policy\s+Term"),
        "premium_payment_term_years": _label_int(one_line, r"Premium\s+Paying\s+Term"),
        "premium_mode": _label_text(
            one_line,
            r"Premium\s+Mode",
            r"[A-Za-z-]+",
        ),
        "guaranteed_additions": _label_money(
            one_line,
            r"Bonus\s*,?\s*G(?:uar|ur)anteed(?:\s+Addition)?",
        ),
    }


def _label_text(text: str, label: str, value: str, *, stop: str = "") -> str | None:
    suffix = f"(?={stop})" if stop else ""
    match = re.search(rf"\b{label}\s*:\s*({value}){suffix}", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _label_money(text: str, label: str) -> str | None:
    match = re.search(
        rf"\b{label}\s*:?\s*(?:₹|Rs\.?|INR)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        text,
        re.IGNORECASE,
    )
    return _to_number_string(match.group(1)) if match else None


def _label_date(text: str, label: str) -> str | None:
    match = re.search(
        rf"\b{label}\s*:?\s*(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    raw = match.group(1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    from datetime import datetime

    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _label_int(text: str, label: str) -> int | None:
    value = _label_text(text, label, r"\d{1,3}")
    return int(value) if value else None


def _mask_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return value if value.startswith("****") else f"****{value[-4:]}"


def _same_identifier(left: str | None, masked_right: object) -> bool:
    if not left or not isinstance(masked_right, str):
        return False
    return left[-4:] == masked_right[-4:] and len(left) > 4


def _first_not_none(*values: str | None) -> str | None:
    return next((value for value in values if value is not None), None)


def _policy_type_from_name(policy_name: str | None) -> PolicyType | None:
    if not policy_name:
        return None
    normalized = policy_name.lower().replace("-", " ")
    if "ulip" in normalized or "unit linked" in normalized:
        return PolicyType.ULIP
    if any(marker in normalized for marker in ("money back", "endowment", "savings")):
        return PolicyType.ENDOWMENT
    if "term" in normalized:
        return PolicyType.TERM
    return None


def extract_from_pdf(
    path: str,
    client: LocalClient | None = None,
    config: Config | None = None,
) -> ExtractionResult:
    """Convenience: pdf_extract → local-model holding extraction."""
    config = config or load_config()
    ocr = config.ocr
    doc = pdf_extract(
        path,
        ocr_mode=ocr.mode if ocr.enabled else "never",
        min_text_chars=ocr.min_text_chars,
        ocr_dpi=ocr.dpi,
        ocr_pipeline_version=ocr.pipeline_version,
    )
    return extract_holdings(doc.full_text, client=client, config=config)
