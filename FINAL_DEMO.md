# Setu Final Demo Runbook

This runbook uses only synthetic data. The demo database is `data/setu-demo.db`; resetting it does
not alter the personal ledger at `data/setu.db`.

## One-time setup

1. Ensure `.env` contains a personal `SETU_DASHBOARD_PASSWORD` of at least 12 characters.
2. Keep the personal `ANTHROPIC_API_KEY` in the same gitignored `.env` only if the Ask Setu step
   will be demonstrated. Setu pins it to `https://api.anthropic.com` and rejects inherited
   corporate gateways.
3. Start Ollama and ensure the configured extraction model is available:

```bash
ollama serve
ollama pull qwen2.5:7b
```

## Preflight

From the repository root, run:

```bash
uv sync
uv run setu evaluate --live-model
uv run pytest -q
```

Expected evaluation results:

- 6/6 document classifications
- 4/4 golden reconciliations, including the HDFC bank balance
- mismatch escalation triggered
- exact net-worth ground truth
- 7/7 investment positions with source-backed ROI evidence in the demo corpus
- 0 unsafe term-policy valuations
- current, short-term, and long-term risk scenarios evaluated from five deterministic components
- no raw-document tool exposed to Claude
- 7/7 exact local-model holding extractions

The verified regression baseline is 110 passing tests.

## Launch

```bash
uv run setu demo --reset
```

This creates a clean, source-linked synthetic ledger and opens `http://127.0.0.1:8765`. The six
source PDFs are in `data/synthetic/`.

## Suggested 8–10 minute story

1. **Problem (30 seconds).** Financial data is split across US brokerage and retirement accounts,
   Indian mutual funds and banks, and insurance documents with different value meanings.

2. **Architecture (45 seconds).** LangGraph coordinates local document extraction, deterministic
   reconciliation, human review, and idempotent SQLite persistence. Ollama handles document text
   locally. Claude can explain sanitized results through approved calculation tools; it never sees
   raw PDF text.

3. **Grounded financial picture (90 seconds).** Show the dashboard values:

   - Net worth: **$275,488.50**
   - Investment current value covered by cost basis: **$262,135.20**
   - Cost basis / invested amount: **$183,045.00**
   - Unrealized gain: **$79,090.20**
   - Document-backed ROI: **43.21%**
   - ROI evidence coverage: **100% of investment value in the synthetic corpus**

   Explain that ROI excludes cash, insurance, fees, taxes, and distributions. If cost is absent,
   Setu shows “unknown” instead of guessing.

4. **Risk over time (90 seconds).** Open “Portfolio health.” The explainable score is **37/100**
   (“Needs attention”), with all three horizons evaluated:

   - Current: elevated because several independent indicators are outside the declared profile.
   - Short term: cash is **0.7%** of investable assets and covers **76.2%** of the three known
     premiums due within 12 months; living expenses are still unknown.
   - Long term: equity is **85.0%** versus a **65.0%** target, Apple is **30.3%** of investable
     assets, and USD exposure is **87.1%** versus a **60.0%** guardrail.

   Show the five score components and the review actions. Explain that this is a deterministic
   diagnostic, not a suitability rating or a prediction.

5. **Decision support (45 seconds).** Open “What needs attention.” Point out the largest position,
   currency guardrail, allocation drift, and evidence-backed next reviews. Setu suggests questions
   and planning steps; it does not name a security to buy or execute a rebalance.

6. **Insurance safety (60 seconds).** Open a policy. Show coverage separately from current asset
   value. Term coverage is excluded from net worth; ULIP/endowment values require stated fund or
   surrender evidence. The LIC policy deliberately has no current surrender value, so Setu shows an
   explicit data gap instead of rejecting the policy or inventing a value.

7. **User control and provenance (60 seconds).** In Data sources, turn one statement off. Net worth,
   ROI coverage, allocations, and insights recalculate immediately. Turn it back on. No record is
   deleted.

8. **Ingestion safeguards (60 seconds).** Upload one of the already seeded synthetic PDFs. Setu
   identifies the exact file hash and reports it as already imported, demonstrating idempotency.
   Mention that the HDFC bank file now follows a dedicated balance path: closing balance is
   extracted without an LLM and reconciled against available balance.

9. **Grounded Q&A (optional, 60 seconds).** Ask: “Explain my current, short-term, and long-term
   risks. What should I review first, and what important data is missing?” Show the readable answer,
   tool names beneath it, and the sanitized-cloud notice.

The complete data story and score math are documented in
[`SYNTHETIC_DEMO_SCENARIO.md`](SYNTHETIC_DEMO_SCENARIO.md).

## Recovery

- Rebuild only the demo data: `uv run setu demo --reset`.
- If the model is unavailable: start Ollama and rerun `uv run setu evaluate --live-model`.
- If the dashboard does not open: confirm the password exists, then use
  `uv run setu demo --reset --no-open` and browse to `http://127.0.0.1:8765`.
- Do not use `setu seed --fresh` on the personal ledger for a rehearsal; the isolated `setu demo`
  command exists to avoid that risk.
