# Setu Synthetic Demo Scenario

This corpus represents one fictional cross-border professional with assets in the United States and
India. Every name, account reference, amount, and document is synthetic. The scenario is deliberately
unbalanced so Setu can demonstrate analysis, uncertainty, and safe next steps—not only list assets.

## Source documents

| Source | What it tests |
|---|---|
| Fidelity brokerage | Three securities, source-stated cost basis, a large single-stock gain, and one bond loss |
| Fidelity 401(k) | Retirement holdings with equity and debt cost basis |
| CAMS mutual-fund folio | Indian number formats, INR conversion, and invested amount as cost basis |
| HDFC savings account | Deterministic bank-balance extraction and short-term cash |
| Tata AIA policy statement | A ULIP with current fund value and a term policy with protection but no asset value |
| LIC policy statement | A valid endowment contract whose current surrender value is not stated |

The statement date is August 15, 2026. Demo conversion uses the configured fixed rate of
`1 INR = 0.01203 USD`, making the run repeatable.

## Portfolio and cost basis

| Position | Current value | Cost basis | Scenario represented |
|---|---:|---:|---|
| Vanguard S&P 500 ETF | $60,000 | $48,000 | Broad US equity gain |
| Apple | $80,000 | $32,000 | Large single-stock concentration and gain |
| Vanguard Total Bond ETF | $10,000 | $11,000 | Loss case; ROI can be negative |
| Fidelity 500 Index | $70,000 | $55,000 | Long-term retirement equity |
| Fidelity US Bond Index | $20,000 | $19,000 | Retirement debt allocation |
| Axis Bluechip Fund | ₹1,200,000 | ₹900,000 | Indian equity and INR exposure |
| HDFC Corporate Bond Fund | ₹640,000 | ₹600,000 | Indian debt and INR exposure |
| HDFC cash | ₹160,000 | Not applicable | Available liquidity |
| Tata AIA ULIP fund value | ₹950,000 | Excluded from investment ROI | Supported insurance asset value |
| Tata AIA term coverage | ₹10,000,000 coverage | Not an asset | Protection must not inflate net worth |
| LIC New Jeevan Anand | ₹1,500,000 coverage | Current value unknown | Missing evidence must remain unknown |

Across the seven investment positions, current value is **$262,135.20**, source-stated cost is
**$183,045.00**, unrealized gain is **$79,090.20**, and document-backed ROI is **43.21%**. All seven
positions have cost evidence. Cash and insurance are excluded from that ROI calculation. Total net
worth is **$275,488.50**; it includes the stated ULIP fund value but excludes term coverage and the
LIC policy with no stated current surrender value.

## Risks the scenario should surface

The declared profile targets 65% equity, 25% debt, and 10% cash, with no more than 60% of total net
worth in USD. The portfolio instead has:

- **85.0% equity** of investable assets, showing long-term allocation skew.
- **Apple at 30.3%** of investable assets, showing single-position concentration.
- **87.1% USD exposure**, showing currency mismatch against the declared guardrail.
- **0.7% cash**, far below the 10% target.
- Three annual premiums totaling **₹210,000 ($2,526.30)** due within 12 months. Available cash is
  **₹160,000 ($1,924.80)**, or **76.2%** of those known commitments.
- One valuation gap: the LIC document proves the contract and coverage but does not state a current
  surrender value.

## Explainable health result

Setu gives this scenario **37/100 — Needs attention**. It is a deterministic diagnostic, not an
investment suitability rating or market forecast.

| Component | Score | Reason |
|---|---:|---|
| Target alignment | 5/25 | The equity/debt/cash mix is materially away from the declared target |
| Position concentration | 5/20 | Apple is 30.3% of investable assets |
| Currency exposure | 1/15 | USD exposure is 27.1 percentage points above the guardrail |
| Short-term liquidity | 8/20 | Cash is below target and does not cover all known premiums |
| Data completeness | 18/20 | Cost and source evidence are strong, but one savings-policy value is missing |

Current, short-term, and long-term status are all **elevated**, for different reasons. This is useful
in the demo because Setu can show which evidence drove each result rather than repeat one generic risk
label.

## Safe review suggestions and known limits

Setu asks the user to review the near-term cash buffer, consider how future contributions or a
separately approved rebalance could reduce allocation drift, review the large Apple position, match
USD/INR exposure to future spending, and obtain a current LIC surrender-value statement. It does not
place trades or name a security to buy.

The score also says what it cannot know yet: monthly essential expenses and emergency-reserve goal;
future goals with dates, amounts, and currencies; liabilities, income stability, dependents, and tax
constraints; and the LIC current surrender value. These gaps prevent the dashboard from presenting a
false sense of precision.
