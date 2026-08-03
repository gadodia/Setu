"""Declarative base and shared column types."""

from __future__ import annotations

from sqlalchemy import Numeric
from sqlalchemy.orm import DeclarativeBase

# Money: fixed-precision Decimal, never float. 20 digits, 4 after the point —
# enough for INR crore-scale sums and paisa precision. Used as the column type:
#   market_value: Mapped[Decimal] = mapped_column(Money, ...)
Money = Numeric(20, 4)

# Quantity: fund units / share counts can be fractional to many places.
Quantity = Numeric(20, 6)


class Base(DeclarativeBase):
    pass
