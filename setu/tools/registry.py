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
from setu.tools import calc, fx
from setu.tools.insights import (
    build_portfolio_insights,
    compute_investment_performance,
    compute_portfolio_health,
)

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
        "name": "analyze_portfolio",
        "description": "Return deterministic, source-backed investment performance and ranked "
                       "portfolio attention signals. ROI is included only where statements "
                       "provide cost basis; use this for return, concentration, currency-risk, "
                       "allocation-drift, short/long-term risk, health-score, and data-gap questions.",
        "input_schema": {"type": "object", "properties": {}},
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

        if name == "analyze_portfolio":
            nw = calc.compute_net_worth(session, config)
            performance = compute_investment_performance(nw)
            portfolio_insights = build_portfolio_insights(
                session,
                config,
                net_worth=nw,
            )
            health = compute_portfolio_health(session, config, net_worth=nw)
            return {
                "base_currency": nw.base_currency,
                "performance": performance.as_dict(),
                "insights": [insight.as_dict() for insight in portfolio_insights],
                "health": health.as_dict(),
                "limitations": (
                    "ROI excludes positions without source-stated cost basis, cash, insurance, "
                    "fees, taxes, and distributions. The health score is a deterministic "
                    "portfolio diagnostic, not investment advice or a suitability assessment."
                ),
            }

        raise ValueError(f"Unknown tool: {name!r}")

    return dispatch
