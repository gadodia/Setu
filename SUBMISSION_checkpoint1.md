# Setu: A Cross-Border Wealth & Portfolio Agent

**CMU Agentic AI Capstone — Checkpoint 1: Problem Framing & System Design**

## The agent, the problem, and the intended user

I am building a Personal Assistant agent, *Setu* (Hindi for "bridge"), that consolidates and analyzes
an individual's **wealth** spread across the United States and India. A cross-border household holds
assets in a dozen institutions — US brokerage and retirement accounts (401k/IRA), Indian mutual funds,
bank balances, and insurance/endowment policies (LIC, Tata) — denominated in different currencies and
reported in incompatible statement formats. No single institution offers a unified view, so
understanding **net worth, asset allocation, and portfolio risk** requires tedious, error-prone manual
aggregation. Crucially, this is a *wealth* problem, not an expense-tracking one: the user's real
questions are "what am I worth, how is it allocated across asset classes, geographies, and currencies,
and does that match my risk appetite?" Setu ingests statements, normalizes them into one
currency-aware view of holdings and balances, analyzes allocation and concentration, and measures the
portfolio against a user-declared target risk profile. The intended user is an individual managing
their own cross-border wealth (my own situation is the archetype).

## Why a standalone LLM is insufficient

A single prompt cannot solve this. First, it depends on *current external data* — foreign-exchange
rates and fund NAVs — that lies outside any model's training data. Second, it demands *exact
arithmetic*: net worth, allocation percentages, and currency exposures must be computed
deterministically, because language models routinely miscalculate. Third, the work is inherently
*multi-step and stateful*: parse a heterogeneous statement, classify each holding by asset class and
geography, extract quantities and values, deduplicate across statements, convert currencies, then
reason over the consolidated portfolio. Fourth, reliability requires *verification loops* — parsed
totals must reconcile against each statement's stated balance before any figure is trusted. These
properties require an agent workflow rather than one-shot generation.

## Environment

Setu operates over: (1) *Documents* — synthetic, holdings-rich statements: brokerage and mutual-fund
holdings with quantities and NAVs, retirement summaries, ULIP fund values, endowment
surrender/maturity values, and bank balances. (2) *A user-declared target risk profile* (asset-class,
geography, and currency targets) that drives the advice loop. (3) *Tools and data sources* — a
PDF/CSV extractor, an FX-rate lookup, a deterministic calculator (net worth, allocation, exposure), a
risk analyzer (actual-vs-target, concentration), a policy-value selector, a reconciler, and a
knowledge base of policy-type rules; plus a normalized datastore and a retrieval memory. (4) *Users* —
a single trusted individual who provides documents, sets the risk profile, corrects the agent, and
receives reports.

## Actions the agent takes

To make progress, Setu must: read and parse documents and classify each account and holding; extract
holdings, balances, and policy values; deduplicate entries across statements; look up FX rates and
normalize every value to a base currency; reconcile computed balances against reported totals and flag
discrepancies; consolidate everything into net-worth and asset-allocation views; **analyze portfolio
risk** — concentration by stock, sector, or currency, and equity-versus-debt balance; **compare actual
allocation against the user's target profile and explain any drift**; detect wealth commitments
(insurance premiums, loan EMIs) and schedule reminders; and answer natural-language questions such as
"am I over-concentrated in US tech?" or "what is my real INR exposure?" For insurance, which has no
market price, the agent draws valuation *semantics* from a knowledge base (term policies count as
coverage, not assets; endowments use surrender value; ULIPs use units × NAV) while taking the *numbers*
only from documents — never inventing them. When an extraction is ambiguous, it asks rather than
guessing.

## How feedback guides behavior across steps

Feedback operates at several levels. *Reconciliation* is the primary internal signal: if parsed values
do not match a statement's stated total, the agent re-parses (exploring multiple interpretations) or
escalates to the user before proceeding. *Confidence thresholds* route low-certainty extractions to
human-in-the-loop confirmation. *The target risk profile* provides the primary external feedback loop —
measured drift between actual and desired allocation drives the agent's advice. *User corrections* are
stored and retrieved to improve future classification. Before presenting any view, a *self-consistency
check* confirms allocations and per-currency subtotals sum correctly. This layered feedback turns a
brittle pipeline into a reliable, self-correcting agent.

## Scope

The 7-week build focuses on portfolio consolidation, allocation and risk analysis, and risk-appetite
alignment on synthetic data. Live API integration and news-driven forecasting are staged as extensions.
