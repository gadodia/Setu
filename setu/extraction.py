"""LLM-based holding extraction — statement text → structured, validated holdings.

The PII-heavy step runs on the LOCAL model (Ollama) so raw statement text never leaves the
machine. Output is constrained to a pydantic schema (Ollama structured outputs), then validated
here. The model classifies and transcribes; it does NOT compute — market values are read from the
statement as-is, and reconciliation (Week 4) later verifies them against the stated total.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, field_validator

from setu.config import Config, load_config
from setu.llm.local import LocalClient
from setu.models import AssetClass, Geography
from setu.tools.pdf_extract import extract as pdf_extract


class ExtractedHolding(BaseModel):
    symbol: str | None = Field(default=None, description="Ticker/symbol if present, else null.")
    name: str = Field(description="Security or fund name as printed.")
    asset_class: AssetClass = Field(description="EQUITY, DEBT, CASH, INSURANCE_CASH_VALUE, or REAL_ASSET.")
    geography: Geography = Field(description="US or INDIA.")
    quantity: str = Field(default="0", description="Units/shares as a decimal string.")
    market_value: str = Field(description="Market value in the statement's currency, decimal string.")
    currency: str = Field(description="ISO currency code, e.g. USD or INR.")

    @field_validator("market_value", "quantity")
    @classmethod
    def _valid_decimal(cls, v: str) -> str:
        try:
            Decimal(str(v).replace(",", "").replace("$", "").strip() or "0")
        except InvalidOperation as e:
            raise ValueError(f"not a valid number: {v!r}") from e
        return v

    def as_decimal(self, field: str) -> Decimal:
        raw = getattr(self, field)
        return Decimal(str(raw).replace(",", "").replace("$", "").strip() or "0")


class ExtractionResult(BaseModel):
    holdings: list[ExtractedHolding] = Field(default_factory=list)


_SYSTEM = (
    "You extract investment holdings from a financial statement's raw text. "
    "Transcribe values EXACTLY as printed — do not compute, round, or invent anything. "
    "Classify each row's asset_class and geography. If a value is absent, omit the holding. "
    "Return only holdings that are securities/funds (not cash balances or insurance policies)."
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
