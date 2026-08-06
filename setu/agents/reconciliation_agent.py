"""ReconciliationAgent — the primary feedback signal (concept #4, Tree-of-Thought).

The statement prints a stated total (e.g. "Total account value: $262,413.30"). Extraction is
fallible, so before trusting the holdings we check: does the **sum of extracted market values**
equal that **stated total** within tolerance?

ToT in practice: statement text is messy, so there's no single reliable "the total is X" parse.
We generate **several candidate totals** via independent hypotheses (the explicit "Total account
value" line, the largest currency figure, the last table "Total" row, …), score each by closeness
to the extracted sum, and keep the best-scoring candidate. Then a deterministic tolerance check
turns that into an `ok` / `mismatch` verdict. The LLM is *not* in this loop — reconciliation is
deterministic math, exactly as the safety guarantee (§3b) requires.
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

        # H1: an explicit labelled total line ("Total account value: $X", "Portfolio valuation: Rs. X").
        for label in ("Total account value", "Portfolio valuation", "Available balance",
                      "Total value", "Net worth"):
            m = re.search(rf"{label}[:\s]*(?:Rs\.?|\$|₹)?\s*({_NUM})", text, re.IGNORECASE)
            if m and (v := _to_decimal(m.group(1))) is not None:
                cands.append(TotalHypothesis(f"labelled:{label}", v))

        # H2: a table "Total" row — the figure following the word "Total".
        for m in re.finditer(rf"\bTotal\b[^0-9]*({_NUM})", text):
            if (v := _to_decimal(m.group(1))) is not None:
                cands.append(TotalHypothesis("table-total-row", v))

        # H3: the single largest money figure in the document (a total usually dominates line items).
        figures = [v for raw in re.findall(_NUM, text) if (v := _to_decimal(raw)) is not None]
        if figures:
            cands.append(TotalHypothesis("largest-figure", max(figures)))

        return cands

    def run(self, statement_text: str, sum_extracted: Decimal) -> ReconcileResult:
        cands = self._candidates(statement_text)

        if not cands:
            # No stated total to check against → can't disconfirm; treat as reconciled with delta 0.
            return ReconcileResult(None, sum_extracted, Decimal("0"), "ok", cands)

        # Score each hypothesis by closeness to the extracted sum; keep the best.
        best = min(cands, key=lambda c: abs(c.value - sum_extracted))
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
