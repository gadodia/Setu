# Setu — Personas & Memory Design

> Companion to `ARCHITECTURE.md`. Addresses the checkpoint-1 review feedback: make the agent
> **persona-aware** (cater financial literacy/strategy to each user type) and specify the **memory
> architecture** that lets it do so. Design principle inherited from the architecture doc:
> **the LLM decides/classifies/explains; deterministic Python tools compute; every claim is
> traceable; latent preferences are *asked*, never invented.**

---

## Part 1 — The `ProfilingAgent` (a dedicated persona agent)

### Why it's a separate agent
It sits alongside `IngestionAgent` / `ReconciliationAgent` / `InsightsAgent` under the orchestrator and
does one job: **given the reconciled portfolio + user-declared facts, determine who this investor is
and what they need.** Kept separate because:
- **Separation of concerns** — Insights/Forecast agents *consume* a shared profile instead of each
  re-deriving "who is this person."
- **It's a distinct reasoning task** — classification + goal elicitation, not computation or retrieval.
- **Auditable in isolation** — we can show *why* a user was classified, and let them correct it (which
  feeds the same `preferences` + vector-store learning loop the rest of Setu already uses).

### The observable-vs-latent split (the honesty guardrail)
Only one kind of signal is inferable from data. Pretending otherwise is exactly the "confident
hallucination" the architecture forbids.

| Signal type | Inferable from statements/age? | Examples | How Setu gets it |
|---|---|---|---|
| **Observable / derivable** | ✅ deterministic | asset mix, concentration, US/India split, USD/INR exposure, account types (taxable/401k/IRA/demat/MF), portfolio size, cash drag, dividend reliance, realized-gain hints | `profile_features.py` computes from the ledger — **no LLM math** |
| **Latent / preference** | ❌ must be asked | risk *tolerance*, goals (retirement/house/education), time horizon, liquidity needs, ESG prefs | short HITL elicitation (LangGraph `interrupt`) |

Key quant distinction baked in: **risk *capacity*** (what the finances can absorb — computable) vs.
**risk *tolerance*** (what the user will emotionally bear — only knowable by asking). A young earner
has high capacity but may have low tolerance; the agent must not conflate them.

### ProfilingAgent flow
1. **Derive** observable features deterministically (`tools/profile_features.py`).
2. **Propose** a candidate persona + confidence, *with evidence* ("you look like a **Cross-Border
   Accumulator**: 82% equity, 65% USD exposure, 100% in taxable+401k, age 31").
3. **Ask** a small targeted set of questions to resolve latent gaps (tolerance, goals, horizon).
4. **Persist** the confirmed `RiskProfile` + persona to SQLite; embed the rationale + corrections into
   the vector store so future runs recall them.

### Design decision: fixed archetypes on a feature-vector substrate
Use a **fixed set of 5 named archetypes** for explainability (the user-facing label), backed by an
**underlying feature vector** as the evidence (the derivable signals). Archetypes are the *pitch*;
the vector is the *proof*. This also keeps the ties back to the architecture's target-allocation loop
(§0.4): each persona ships a **default target allocation** the user can override.

---

## Part 2 — The five personas

Each persona = *derivable fingerprint* (what flags it) + *latent questions* (what must be asked) +
*default strategy focus* + *literacy framing* (how the InsightsAgent should explain things). These map
directly onto the strategy/quant tools from the checkpoint-1 review's third note.

### P1 — Early Accumulator
- **Fingerprint:** age < ~35; high equity %; small-but-growing balance; few account types; long runway;
  positive savings signal.
- **Ask:** tolerance (capacity is high, tolerance unknown); goal (house? FI?); horizon.
- **Strategy focus:** growth, tax-advantaged contribution room, avoiding over-diversification, cost/fee
  drag, dollar-cost-averaging discipline.
- **Literacy framing:** foundational — explain *why* equity-heavy is defensible at this age, what a
  Sharpe ratio means, why fees compound.

### P2 — Cross-Border Professional / NRI  *(Setu's signature persona)*
- **Fingerprint:** meaningful holdings in **both** US (401k/IRA/brokerage) **and** India (MF/demat/
  LIC); high single-currency (usually USD) exposure; mixed account types across jurisdictions.
- **Ask:** where they intend to retire (drives base currency & tax lens); repatriation plans; horizon.
- **Strategy focus:** **currency-exposure analysis & hedging**, cross-border **tax** (DTAA, PFIC on
  Indian MFs held by US persons, FBAR — ties to `tax.py` extension), duplicate-exposure detection
  (US and India funds both holding the same mega-caps).
- **Literacy framing:** the "two-halves-of-one-portfolio" view; currency risk as a first-class risk.

### P3 — Peak-Earning Wealth Builder
- **Fingerprint:** age ~35–55; large balance; multiple account types; possibly concentrated (RSUs/
  single-stock); mix of taxable + tax-advantaged.
- **Ask:** goals (education, second home, early retirement), tolerance, liquidity needs.
- **Strategy focus:** **concentration/diversification** (RSU single-stock risk), **rebalancing** drift,
  **tax-loss harvesting**, factor/sector exposure, asset *location* (which assets in which account type).
- **Literacy framing:** intermediate — efficient-frontier tradeoffs, why concentration ≠ diversification.

### P4 — Pre-Retiree / Capital Preserver
- **Fingerprint:** age ~55+; shifting toward debt/cash; endowment/annuity policies present; larger,
  stable balance; income-oriented holdings.
- **Ask:** target retirement date, income needs, tolerance (usually lower), legacy intent.
- **Strategy focus:** **sequence-of-returns risk**, glide-path de-risking, **Monte Carlo retirement
  projection** ("P(you hit your income goal)"), drawdown/VaR framing, income vs. growth.
- **Literacy framing:** preservation & income — downside metrics (max drawdown, CVaR) over upside.

### P5 — Income-Focused / Retiree
- **Fingerprint:** low equity %; high debt/cash/dividend reliance; drawdown phase; annuity/endowment
  cash values material to net worth.
- **Ask:** monthly income requirement, essential-vs-discretionary split, longevity assumption.
- **Strategy focus:** sustainable withdrawal rate, income durability, inflation erosion, minimizing
  volatility, currency stability (esp. for the NRI overlap).
- **Literacy framing:** cash-flow-first, plain-language, low-jargon; protect against outliving assets.

> **Overlap is expected, not a bug.** The NRI dimension (P2) can co-occur with any life stage — the
> feature vector captures that (e.g. "P3 with strong P2 cross-border signal"); the archetype is just
> the dominant label. This is why the substrate is a vector and the label is a projection of it.

---

## Part 3 — Memory architecture

The architecture doc already commits to **SQLite (truth) + vector sidecar (semantic) + LangGraph
SQLite checkpointer**. That's the *storage*. This section maps the four cognitive **memory types** the
review asked about onto that storage, and says what each holds — per agent and per persona.

### The four memory types → where each lives

| Memory type | Lifespan / scope | What it holds for Setu | Backing store |
|---|---|---|---|
| **Working** | one graph run; ephemeral | current goal, tools called this run, intermediate parse/reconcile state, the profile loaded for this session, in-flight ToT hypotheses | **LangGraph State** (`graph/state.py`) — the TypedDict passed between nodes; discarded after the run |
| **Short-term** | current conversation/session; resumable | recent Q&A turns, the pending `ask_user` question, "what we just showed you," last report context | **LangGraph checkpointer** (SQLite-backed) — durable across a multi-step/interrupted run |
| **Long-term (semantic)** | persistent facts & knowledge | the **confirmed persona + RiskProfile**, user preferences/corrections, policy-rules KB, parsing/format knowledge, ticker→sector reference | **SQLite** (`preferences`, `RiskProfile`, structured facts) + **`knowledge/*.yaml`** KBs |
| **Long-term (episodic)** | history of what happened | past task executions ("last time a Tata ULIP statement looked like this, the NAV field was here"), prior reconciliations, past corrections and their outcomes | **`memory/run_history.py`** + **vector store** (embedded for similarity recall) |

This is not new infrastructure — it's a **naming of the layers Setu already has**. The review's
"short/long/episodic/working" vocabulary maps cleanly onto State / checkpointer / SQLite+KB / run-history+vectors.

### Working memory (per-run) — what each agent keeps in State
- **Orchestrator:** current goal, plan, which sub-agents dispatched, observations, re-plan count.
- **IngestionAgent:** raw extracted text, candidate holdings, confidence scores (pre-commit).
- **ReconciliationAgent:** the N ToT parse hypotheses + their scores vs. stated total (transient).
- **ProfilingAgent:** derived feature vector for this run + candidate persona (before confirmation).
- **InsightsAgent:** retrieved context + tool results assembled for the current answer.

### Short-term memory (per-session) — checkpointer
Holds the conversation thread and any **pending human-in-the-loop interrupt** so a run can pause on
`ask_user` (e.g. "is this a ULIP or endowment?", "what's your target retirement date?") and resume on
reply without losing state. This is what makes the ProfilingAgent's elicitation step and the
ReconciliationAgent's mismatch-interrupt work.

### Long-term semantic memory — the persona lives here
- **`RiskProfile` + persona** (SQLite): the confirmed archetype, its feature vector, the default and
  user-overridden target allocation. Loaded into working memory at the start of every run so **all**
  agents act persona-aware.
- **`preferences` / `user_corrections`** (SQLite, also embedded): "user reclassified this LIC plan as
  endowment," "user prefers INR as base currency," "user's stated tolerance = moderate."
- **Knowledge bases** (`policy_rules.yaml`, future `tax_rules.yaml`, ticker→sector table): dated,
  sourced, model-applied-not-invented facts.

### Long-term episodic memory — how Setu gets smarter
- **`run_history`** logs each task execution (inputs, tools used, outcome, corrections).
- Embedded into the **vector store** so the agent can retrieve *"a situation like this one before"* —
  the graded RAG-memory demo (concept #3): recall a past statement-format quirk, a past reconciliation
  strategy that worked, or a past correction on a similar holding.

### Per-persona memory nuance
The memory *types* are the same for everyone; what differs is **what's salient to retrieve**:

| Persona | Episodic recall biased toward | Long-term facts that matter most |
|---|---|---|
| P1 Early Accumulator | past fee/allocation nudges | contribution room, savings-rate trend |
| P2 Cross-Border/NRI | past currency-exposure & tax explanations, jurisdiction-specific parse quirks | base-currency choice, residency/retirement intent, PFIC/DTAA flags |
| P3 Wealth Builder | past concentration warnings, rebalancing history | RSU vesting cadence, target allocation, asset-location prefs |
| P4 Pre-Retiree | past glide-path/projection runs | retirement date, income need, policy maturity values |
| P5 Retiree/Income | past withdrawal-rate discussions | monthly income requirement, longevity assumption |

Practically: the InsightsAgent's retrieval query is **seasoned with the active persona**, so a retiree's
question surfaces income/drawdown episodes while an accumulator's surfaces growth/fee episodes — same
store, persona-weighted recall.

---

## Part 4 — How this changes the code structure (deltas to `ARCHITECTURE.md §4`)

Additive only — nothing re-architected:
- `setu/agents/profiling_agent.py` — the new ProfilingAgent.
- `setu/tools/profile_features.py` — deterministic derivation of the observable feature vector.
- `setu/knowledge/persona_rules.yaml` — the 5 archetypes: their fingerprints, default target
  allocations, and literacy-framing hints (model-applied, user-overridable).
- `setu/models/` — extend `RiskProfile` to store persona label + feature vector (already holds target
  allocation).
- `memory/` — no new store; `run_history.py` + `vectorstore.py` already cover episodic/semantic. Add a
  `persona` field to the retrieval query so recall is persona-weighted.

The graded-concept mapping is unchanged and actually *reinforced*: ProfilingAgent adds a second clear
**multi-agent** member (concept #5) and a second **HITL** touchpoint (concept #6), and the four-type
memory framing sharpens the **Memory/RAG** story (concept #3).
