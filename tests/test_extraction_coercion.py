"""Regression tests for money-value coercion in holding extraction.

Small local models sometimes emit `market_value` as a nested {amount, currency} object or its
Python-repr string instead of a bare number. The schema must normalize these rather than reject
them. These tests pin the exact shapes observed from qwen2.5:7b during live `setu ingest`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from setu.extraction import ExtractedHolding, ExtractionResult, _to_number_string
from setu.models import AssetClass, Geography


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("60000.00", "60000.00"),
        ("$44,000.00", "44000.00"),
        ("₹1,200,000", "1200000"),
        ("", "0"),
        # The exact bug: a stringified dict-repr with u'...' prefixes.
        ("{u'amount': 60000.0, u'currency': u'USD'}", "60000.0"),
        # A real dict (if a future model/schema returns structured JSON).
        ({"amount": 44000.0, "currency": "USD"}, "44000.0"),
        ({"value": "11000.00"}, "11000.00"),
        # A bare float/int.
        (90000.0, "90000.0"),
    ],
)
def test_to_number_string(raw, expected):
    assert _to_number_string(raw) == expected


def _holding(market_value):
    return ExtractedHolding(
        name="Vanguard S&P 500 ETF",
        asset_class=AssetClass.EQUITY,
        geography=Geography.US,
        quantity="120",
        market_value=market_value,
        currency="USD",
    )


def test_holding_coerces_stringified_dict():
    h = _holding("{u'amount': 60000.0, u'currency': u'USD'}")
    assert h.market_value == "60000.0"
    assert h.as_decimal("market_value") == Decimal("60000.0")


def test_holding_coerces_real_dict():
    h = _holding({"amount": 44000.0, "currency": "USD"})
    assert h.as_decimal("market_value") == Decimal("44000.0")


def test_holding_plain_string_still_works():
    h = _holding("$60,000.00")
    assert h.as_decimal("market_value") == Decimal("60000.00")


def test_invalid_value_still_rejected():
    with pytest.raises(ValueError):
        _holding("not-a-number")


def test_extraction_result_parses_bug_shape_from_json():
    """The whole ExtractionResult validates even when the model nests money as a string."""
    payload = (
        '{"holdings": [{"name": "Apple Inc.", "asset_class": "EQUITY", "geography": "US", '
        '"quantity": "200", "market_value": "{u\'amount\': 44000.0, u\'currency\': u\'USD\'}", '
        '"currency": "USD"}]}'
    )
    result = ExtractionResult.model_validate_json(payload)
    assert result.holdings[0].as_decimal("market_value") == Decimal("44000.0")
