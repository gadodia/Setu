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

from pydantic import BaseModel, Field, field_validator

from setu.config import Config, load_config
from setu.llm.local import LocalClient
from setu.models import AssetClass, Geography
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

    def as_decimal(self, field: str) -> Decimal:
        return Decimal(_to_number_string(getattr(self, field)))


class ExtractionResult(BaseModel):
    holdings: list[ExtractedHolding] = Field(default_factory=list)


_SYSTEM = (
    "You extract investment holdings from a financial statement's raw text. "
    "Transcribe values EXACTLY as printed — do not compute, round, or invent anything. "
    "Classify each row's asset_class and geography. If a value is absent, omit the holding. "
    "Return only holdings that are securities/funds (not cash balances or insurance policies). "
    "IMPORTANT: `market_value` and `quantity` must each be a PLAIN number as a string "
    '(e.g. "60000.00") — never an object, never with a currency symbol or commas. '
    "The currency code goes only in the separate `currency` field."
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
    return client.extract_structured(prompt, ExtractionResult, system=_SYSTEM)


def extract_from_pdf(
    path: str,
    client: LocalClient | None = None,
    config: Config | None = None,
) -> ExtractionResult:
    """Convenience: pdf_extract → local-model holding extraction."""
    doc = pdf_extract(path)
    return extract_holdings(doc.full_text, client=client, config=config)
