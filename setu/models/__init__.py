"""SQLAlchemy ORM models — the Setu ledger (source of truth).

The domain is numeric and relational, so this is the primary store (see ARCHITECTURE.md §2).
Money is stored as ``Numeric`` (maps to Python ``Decimal``) — never float — so exact arithmetic
holds end to end. A ``Statement`` carries ``file_hash`` + ``as_of_date`` to make ingestion
idempotent and time-aware (§2a).
"""

from setu.models.base import Base
from setu.models.entities import (
    Account,
    AccountType,
    AssetClass,
    Balance,
    FxRate,
    Geography,
    Holding,
    Institution,
    Obligation,
    PolicyType,
    PolicyValue,
    RiskProfile,
    Statement,
    Transaction,
)

__all__ = [
    "Base",
    "Institution",
    "Account",
    "Holding",
    "PolicyValue",
    "Balance",
    "Obligation",
    "FxRate",
    "RiskProfile",
    "Statement",
    "Transaction",
    "AccountType",
    "AssetClass",
    "Geography",
    "PolicyType",
]
