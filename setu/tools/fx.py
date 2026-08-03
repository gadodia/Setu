"""FX conversion — deterministic lookup + exact Decimal conversion.

MVP uses a static rate table from config (rates expressed as *value of 1 unit in the base
currency*). This is the same shape as the future live `price` tool: a tool fetches the rate,
`convert` multiplies deterministically — the LLM never supplies a number. Replaceable with a
live feed without touching callers.
"""

from __future__ import annotations

from decimal import Decimal

from setu.config import Config, load_config


class FxError(ValueError):
    """Raised when a currency has no known rate — surfaced, never silently guessed."""


def rate_to_base(currency: str, config: Config | None = None) -> Decimal:
    """Value of 1 unit of `currency` in the base currency."""
    config = config or load_config()
    currency = currency.upper()
    if currency == config.base_currency.upper():
        return Decimal("1")
    try:
        return config.fx_rates[currency]
    except KeyError as e:
        raise FxError(
            f"No FX rate for {currency!r} → base {config.base_currency!r}. "
            f"Known: {sorted(config.fx_rates)}"
        ) from e


def convert(amount: Decimal, currency: str, config: Config | None = None) -> Decimal:
    """Convert `amount` in `currency` to the base currency (exact Decimal math)."""
    return Decimal(amount) * rate_to_base(currency, config)
