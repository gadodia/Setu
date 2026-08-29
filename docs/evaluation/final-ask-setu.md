# Final Ask Setu Smoke Check

Run date: **August 29, 2026**

This check used only the isolated synthetic demo database. It verifies the personal Claude
integration, bounded tool loop, and Markdown rendering path; it does not send or evaluate a real
financial document.

## Question

> What are the most important risks in this synthetic portfolio, and what evidence supports them?

## Runtime result

| Field | Observed |
|---|---|
| Tool used | `analyze_portfolio` |
| Tool rounds | 2 |
| Stop reason | `end_turn` |
| Truncated | No |
| Output format | CommonMark |
| Rendered HTML | Present |
| Maximum output tokens | 1,200 |
| Maximum tool rounds | 4 |
| Target answer length | 450 words |

## Answer summary

The response below is lightly normalized for line wrapping and ASCII punctuation; its structure and
numeric claims are unchanged.

### Answer

The portfolio's overall health score is **37/100 ("Needs attention")**, driven by four concrete
risks: single-stock concentration, currency concentration, equity/target drift, and thin short-term
liquidity, plus one valuation data gap.

### Key evidence

- **Concentration risk:** Apple Inc. is **29.0% of net worth** and **30.3% of investable assets**. A
  single stock drives nearly a third of the portfolio's outcome. Concentration scored 5/20.
- **Currency risk:** USD exposure is **87.1%**, above the stated **60.0% guardrail** by 27.1
  percentage points. Currency scored 1/15, the weakest component.
- **Allocation drift:** Equity is **85.0%** of investable assets versus a **65.0% target**. About 20%
  of assets would need to shift across equity, debt, and cash to align with that target. Allocation
  scored 5/25.
- **Short-term liquidity:** Cash is **0.7%** of investable assets versus a 10% target and covers only
  **76.2%** of known 12-month obligations ($1,924.80 cash versus $2,526.30 of obligations). Living-
  expense coverage is unknown, so actual liquidity risk may be understated.
- **Data gap:** One insurance policy has no current cash or surrender value on file, so Setu excludes
  it from net worth. The contract and coverage remain visible without an unsupported valuation.

The portfolio also has a **document-backed unrealized gain of $79,090.20 (43.2% ROI)** on $183,045
of cost basis, with cost evidence for all seven investment positions. The return is fully sourced
even though the risk metrics flag structural imbalance.

### What to watch

- Further concentration in Apple or USD-denominated assets would worsen the current imbalance.
- Known cash covers less than 100% of identified 12-month obligations, and living expenses are not
  yet included.
- A current surrender- or fund-value statement is needed to close the remaining policy valuation
  gap.

### Data limits

- ROI excludes cash, insurance, fees, taxes, and distributions.
- The health score is a deterministic diagnostic, not investment advice or a suitability rating.
  It does not yet know the user's goals, liabilities, income stability, or tax constraints.

## Interpretation

The answer used a single approved, sanitized portfolio-analysis tool and did not reach an output or
tool-round limit. Both the raw CommonMark answer and server-rendered HTML were present, confirming the
dashboard rendering contract. Because Claude responses can vary, this artifact records one smoke
check rather than a deterministic accuracy metric.
