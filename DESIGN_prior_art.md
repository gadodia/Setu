# Setu — Prior-Art & Competitive Positioning

> Addresses checkpoint-1 review note #1 ("there's a couple repos that already do this — look into
> that"). A public-sources scan (GitHub, product pages, tech media; Aug 2026) of overlapping projects,
> so Setu can position against **named** alternatives and reuse what's solved instead of rebuilding it.

## Headline: no direct competitor, several architectural peers
No open-source **or** commercial product was found that combines all five of Setu's core traits:
cross-border **US+India** consolidation · multi-format parsing (US brokerage PDF + Indian CAS +
insurance) · currency-normalized net worth/allocation · actual-vs-target risk alignment · an LLM-agent
architecture with a **deterministic math spine**. The overlap is partial and instructive, not competitive.

## The most important finding: our architecture is validated, not novel-in-a-vacuum
Two mature repos independently adopt Setu's exact "LLM narrates, Python computes" principle — strong
evidence for the writeup that the determinism spine is a *proven* pattern, not a personal quirk:
- **FinRobot** (AI4Finance, 7.7k★) — states it verbatim: *"Numbers are code-calculated. Narratives are
  LLM-assisted. Every output is provenance-tracked."* 30 pure-Python financial operators. But it does
  **forward-looking equity research** (DCF/comps/IC memos on public companies), not personal portfolio state.
- **ai-berkshire** (14.9k★) — all math in Python `decimal.Decimal` "because LLM mental math is
  unreliable"; adds cross-validation + Benford's-Law anomaly checks. But it's **stock screening** (what
  to buy), China-focused, not cross-border personal wealth.
- **gpt-investor** (2.3k★) is the **anti-pattern** to cite: it lets the LLM interpret financial numbers
  directly — exactly the hallucination risk Setu's guardrail forbids.

Other peers (not competitors): **virattt/ai-hedge-fund** (62.6k★, multi-persona *simulated* trading),
**augur** (multi-agent + MCP + Bloomberg-style dashboard), **ai-trader** (MCP server exposing
deterministic backtests). Useful patterns to borrow: MCP tool exposure, multi-perspective debate for
divergent advice, information-richness (A/B/C) ratings to counter false confidence.

## What to REUSE (don't reinvent — reviewer's real point)
| Need | Use | Why |
|---|---|---|
| **Indian MF statement parsing** | **`casparser`** (codereverser, 214★, MIT) | Parses CAMS/KFintech/NSDL/CDSL CAS **offline** ("nothing leaves your machine" — fits our PII guardrail), reconciles capital gains "to the paisa," emits Schedule-112A CSV. **This is a solved problem — wrap it in `tools/cas_parse.py`, do not hand-roll.** |
| **Risk metrics** (Sharpe, Sortino, drawdown, VaR, CVaR) | **`quantstats`** (7.5k★) | Actively maintained, pure Python. Powers the "quant equations" direction from review note #3. |
| **Portfolio optimization** (efficient frontier, HRP) — *post-MVP* | **`Riskfolio-Lib`** (4.4k★) or PyPortfolioOpt | For rebalancing/"how should I rebalance?" advice. |
| **Market prices / NAVs** — *extension* | **`yfinance`** (MVP) → **`OpenBB`** (post-MVP, MCP-native) | Slots into the planned `price` tool (§6b). |
| PDF tables | `pdfplumber` + `camelot` | Already in the architecture. |
| **Avoid** | pyfolio/empyrical (legacy), mlfinlab (proprietary license), QuantLib (C++ overkill), zipline (unmaintained) | — |

## What to BUILD (Setu's genuine moat — three underserved intersections)
1. **Cross-border US+India consolidation** — every existing tool is single-country (Wealthfront/
   Betterment ignore India), single-institution (Zerodha Console), or a trading app (INDmoney tracks
   only what you trade *through them*, and has **no AI agent**). Nobody consolidates 401k + LIC + MF +
   brokerage across currencies.
2. **Indian insurance-policy understanding** — no tool auto-classifies Term/Endowment/ULIP and picks
   the right value figure (coverage / surrender / fund-NAV). This is Setu's `policy_value.py` + KB (§5b).
3. **Actual-vs-target risk alignment as read-only advice** — robo-advisors only advise if they *manage
   your money*. Nobody says "you're 85/15 vs your 70/30 target, here's the drift" without taking custody.

## Verification caveats (stated honestly)
- **Morgan Stanley + OpenAI advisor copilot** — the scan could **not** verify this from public sources.
  ⚠️ It's cited in `StudyGuide/IndustryLandscape/finance-insurance.md`; treat that mention as
  **unverified** until confirmed, or soften it in the writeup.
- **Plaid India coverage** — unconfirmed (likely US/UK/EU only) → don't assume Plaid for Indian accounts.
- **India Account Aggregator OSS** — all repos 0–1★, nascent. Do **not** depend on AA for the MVP; use
  manual CAS upload + `casparser`. Revisit post-MVP.
- NRI-tool GitHub search was rate-limited (429) — that slice is incomplete.

## Net effect on the plan
Adopting `casparser` + `quantstats` shrinks the "plumbing" build (exactly what the reviewer flagged as
low-value) and frees effort for the differentiators + the analytics/strategy layer (review note #3).
No re-architecting: both slot into existing tool/agent seams.
