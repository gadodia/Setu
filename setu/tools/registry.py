"""Tool registry — exposes deterministic tools as JSON-schema callables for the LLM (concept #1).

Each entry pairs an Anthropic tool schema with a Python executor. `build_executor` returns the
dispatch function the Claude tool-loop calls; the LLM picks a tool and reads the JSON result, but
every number is computed here in Python — never by the model.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from setu.config import Config, load_config
from setu.tools import calc, fx, pdf_extract

# --- Anthropic tool schemas ------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "fx_convert",
        "description": "Convert an amount from a currency into the base currency using the "
                       "current rate. Use this for any currency conversion — never compute it yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Amount in the source currency."},
                "currency": {"type": "string", "description": "ISO currency code, e.g. INR."},
            },
            "required": ["amount", "currency"],
        },
    },
    {
        "name": "compute_net_worth",
        "description": "Compute total net worth and allocation (by asset class, geography, and "
                       "currency) across the whole ledger, normalized to the base currency. "
                       "Returns exact figures — use this instead of adding numbers yourself.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "pdf_extract",
        "description": "Extract raw text and tables from a PDF statement at the given path. "
                       "Returns text and table rows for you to interpret.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Filesystem path to the PDF."},
            },
            "required": ["path"],
        },
    },
]


def build_executor(session: Session, config: Config | None = None) -> Callable[[str, dict], Any]:
    """Return a dispatch(name, input) -> JSON-serializable result for the tool-calling loop."""
    config = config or load_config()

    def dispatch(name: str, tool_input: dict) -> Any:
        if name == "fx_convert":
            amount = Decimal(str(tool_input["amount"]))
            converted = fx.convert(amount, tool_input["currency"], config)
            return {
                "amount": str(amount),
                "currency": tool_input["currency"].upper(),
                "base_currency": config.base_currency,
                "converted": str(converted),
            }

        if name == "compute_net_worth":
            nw = calc.compute_net_worth(session, config)
            alloc = nw.allocation(nw.by_asset_class)
            return {
                "base_currency": nw.base_currency,
                "net_worth": str(nw.total),
                "by_asset_class": {k: str(v) for k, v in nw.by_asset_class.items()},
                "allocation_fractions": {k: str(v) for k, v in alloc.items()},
                "by_geography": {k: str(v) for k, v in nw.by_geography.items()},
                "by_currency": {k: str(v) for k, v in nw.by_currency.items()},
            }

        if name == "pdf_extract":
            doc = pdf_extract.extract(tool_input["path"])
            return {
                "path": doc.path,
                "text": doc.full_text,
                "tables": doc.all_tables,
            }

        raise ValueError(f"Unknown tool: {name!r}")

    return dispatch
