"""ReconciliationAgent — the primary feedback signal (concept #4, Tree-of-Thought).

The statement prints a stated total (e.g. "Total account value: $262,413.30"). Extraction is
fallible, so before trusting the holdings we check: does the **sum of extracted market values**
equal that **stated total** within tolerance?

ToT in practice: statement text is messy, so there's no single reliable "the total is X" parse.
We generate **several candidate totals** via independent hypotheses (the explicit "Total account
value" line, the last table "Total" row, the largest currency figure, …) and select by
**authority** — the most trustworthy parse rule wins, *independently of* the extracted sum. Picking
the candidate closest to the sum would defeat the whole check: a wrong extraction could pick
whichever subtotal agrees with it. Only after the stated total is chosen do we run a deterministic
tolerance check to get an `ok` / `mismatch` verdict. The LLM is *not* in this loop — reconciliation
is deterministic math, exactly as the safety guarantee (§3b) requires.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from setu.config import Config, load_config

# A money figure like 262,413.30 or 1200000.00 or 1,00,00,000 (Indian grouping).
_NUM = r"[0-9][0-9,]*\.?[0-9]*"


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").replace("$", "").replace("₹", "").strip())
    except (InvalidOperation, AttributeError):
        return None


@dataclass
class TotalHypothesis:
    label: str            # which parse rule produced it (for the trace)
    value: Decimal
    authority: int        # parse-rule priority: lower = more authoritative (0 = explicit labelled total)


@dataclass
class ReconcileResult:
    stated_total: Decimal | None      # the chosen best candidate (None if the doc states no total)
    sum_extracted: Decimal
    delta: Decimal                    # |stated - summed|, 0 when stated_total is None
    status: str                       # "ok" | "mismatch"
    hypotheses: list[TotalHypothesis]


class ReconciliationAgent:
    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.tolerance = Decimal(str(self.config.thresholds.reconcile_tolerance))

    # --- ToT hypothesis generators: each proposes candidate stated totals from the text ----------

    def _candidates(self, text: str) -> list[TotalHypothesis]:
        cands: list[TotalHypothesis] = []

        # H1 (authority 0): an explicit labelled total line ("Total account value: $X",
        # "Portfolio valuation: Rs. X"). This is the statement's own declared total — the most
        # authoritative signal, and the one we prefer regardless of the extracted sum.
        for label in ("Total account value", "Portfolio valuation", "Available balance",
                      "Total value", "Net worth"):
            m = re.search(rf"{label}[:\s]*(?:Rs\.?|\$|₹)?\s*({_NUM})", text, re.IGNORECASE)
            if m and (v := _to_decimal(m.group(1))) is not None:
                cands.append(TotalHypothesis(f"labelled:{label}", v, authority=0))

        # H2 (authority 1): a table "Total" row — a currency-prefixed figure on the same line as
        # the word "Total". Anchored to a currency symbol so "Total shares: 1,995" and a bare
        # "Total" header grabbing a far-off number don't qualify (finding #7).
        for m in re.finditer(rf"\bTotal\b[^\n]*?(?:Rs\.?|\$|₹)\s*({_NUM})", text, re.IGNORECASE):
            if (v := _to_decimal(m.group(1))) is not None:
                cands.append(TotalHypothesis("table-total-row", v, authority=1))

        # H3 (authority 2): the single largest money figure in the document (a total usually
        # dominates line items). Weakest signal — only used when nothing labelled is present.
        figures = [v for raw in re.findall(_NUM, text) if (v := _to_decimal(raw)) is not None]
        if figures:
            cands.append(TotalHypothesis("largest-figure", max(figures), authority=2))

        return cands

    def run(self, statement_text: str, sum_extracted: Decimal) -> ReconcileResult:
        cands = self._candidates(statement_text)

        if not cands:
            # No stated total to check against → can't disconfirm; treat as reconciled with delta 0.
            return ReconcileResult(None, sum_extracted, Decimal("0"), "ok", cands)

        # Select the stated total by AUTHORITY (labelled line > table-total > largest-figure), NOT by
        # closeness to the extracted sum. Choosing the closest candidate would let a wrong extraction
        # pick whichever subtotal line agrees with it and reconcile spuriously (finding #2). Among
        # equal-authority candidates, prefer the largest (a total dominates its own subtotals).
        best = min(cands, key=lambda c: (c.authority, -c.value))
        delta = abs(best.value - sum_extracted)

        # Relative tolerance against the stated total (falls back to absolute if total is 0).
        denom = best.value if best.value != 0 else Decimal("1")
        within = (delta / denom) <= self.tolerance

        return ReconcileResult(
            stated_total=best.value,
            sum_extracted=sum_extracted,
            delta=delta,
            status="ok" if within else "mismatch",
            hypotheses=cands,
        )
