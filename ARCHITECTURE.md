# Setu — Architecture & Path Forward

> **Setu** (सेतु) — Sanskrit/Hindi for "bridge." The agent bridges an individual's finances across
> the US and India into one clear view.

## Context

Setu is the CMU Agentic AI capstone: a **wealth & portfolio agent** that consolidates one
individual's assets across the US and India (brokerage, 401k/IRA, Indian mutual funds, bank
balances, LIC/Tata policy values) — across currencies and incompatible statement formats — into one
**net-worth and asset-allocation picture**, then analyzes portfolio risk and answers questions about
the overall position.

**Focus (important — this is a *wealth* report, not an expense report):** the central object is the
**portfolio** — holdings, balances, and policy values, and how they are *allocated* (by asset class,
geography, and currency) — not day-to-day transactions. The agent's headline job is to answer
"what am I worth, how is it allocated, and does that match my risk appetite?" Spending/transaction
analysis is kept only as a **minor supporting signal** (savings rate, cash flow) and for
premium/EMI reminders framed as *commitments against wealth* — not as a spend-categorization tool.

This is a **greenfield project** (no existing code in the working dir). The 7-week capstone MVP runs
on **synthetic/anonymized statements** (a course requirement), but the architecture is deliberately
built so real data and forecasting layer on later **without re-architecting**.

Confirmed decisions:
- **Model:** Hybrid — local model (Ollama) for PII-heavy raw PDF extraction/redaction; Claude
  (Opus/Sonnet) for reasoning, categorization, reconciliation, Q&A, forecasting.
- **Interface:** Python CLI + a local **"Agent Feed + artifact tiles"** dashboard (see §8) — a
  tiling grid of inspectable panels with a live activity stream, inspired by the RocketSmith sample.
- **Framework:** LangGraph for orchestration (maps onto the graded parse→reason→act loop).
- **Priority:** Grade-ready MVP now, extensible to a real long-term tool.

---

## 0. Core objectives (what Setu must answer)

Ranked — the top items are the point of the project; expenses sit at the bottom as support.

1. **Net worth** — consolidated across all accounts/holdings/policies, in one base currency.
2. **Asset allocation** — the mix by **asset class** (equity / debt / cash / retirement / insurance
   cash value / real assets), by **geography** (US vs India), and by **currency** (USD vs INR exposure).
3. **Portfolio risk analysis** — concentration (over-exposed to one stock / sector / currency?),
   diversification, equity-vs-debt ratio, single-currency dependence.
4. **Risk-appetite alignment (the core "advice" loop)** — the user declares a **target profile**
   (e.g. "aggressive: 70/30 equity/debt, comfortable with INR exposure"); Setu measures **actual vs
   target**, flags drift, and explains it. This is the agent's primary feedback-on-your-finances output.
5. **Commitments against wealth** — insurance premiums, loan EMIs: tracked as liabilities/obligations
   with reminders (a lapsed policy is a *wealth* event, not an expense-tracking one).
6. *(Supporting only)* **Cash-flow signal** — savings rate / net inflow from bank data. Not a
   spend-categorization feature; just enough to inform the wealth picture.

Non-goals for the MVP: detailed expense budgeting, merchant-level spend analytics, transaction-level
categorization as a headline feature.

---

## 1. Model strategy (Hybrid) — who does what

| Task | Model | Why |
|---|---|---|
| Raw PDF/CSV text → structured extraction, PII redaction | **Local (Ollama: Llama 3.1 8B / Qwen2.5)** | Account numbers, balances never leave the machine. Extraction is a bounded task a local model handles adequately. |
| Account/holding classification (asset class, geography, policy type) | **Claude Sonnet** | Needs nuance + few-shot from learned corrections; cheap enough per statement. |
| Reconciliation reasoning, risk/allocation analysis, Q&A, report writing | **Claude Opus 4.8** (or Sonnet for cost) | Highest-stakes reasoning; must be reliable. |
| Forecasting (extension) | **Claude + tools** (market/news APIs) | Multi-step synthesis with sources. |
| Embeddings (semantic categorization/recall) | **Local embedding model** (e.g. `nomic-embed-text` via Ollama) | Keeps merchant strings local; free. |

Key design rule: **exact arithmetic is NEVER done by any LLM.** Balances, FX conversions, subtotals,
net worth are computed by deterministic Python tools. LLMs only extract, classify, explain, and decide.

Config-driven model selection (`config.yaml` → `model_router`) so any stage can be swapped to
cloud-only or local-only without code changes — this is how the "synthetic now, real later" promise
is kept.

---

## 2. Memory & storage — the direct answer: **relational primary + vector sidecar, NO graph DB**

The domain is fundamentally **relational and numeric**, not graph- or vector-shaped. Recommendation:

- **SQLite (source of truth).** The ledger — `accounts`, `institutions`, `transactions`, `holdings`,
  `balances`, `fx_rates`, `obligations`, `statements` (with `file_hash` + `as_of_date` for idempotent,
  time-aware ingestion — see §2a). Chosen because:
  - Exact arithmetic, aggregation, dedup, and reconciliation are SQL's home turf.
  - Single-file, zero-infra, easy to demo and back up. Swappable to Postgres later (SQLAlchemy).
- **Vector store sidecar (Chroma or `sqlite-vec`).** ONLY for semantic tasks:
  - Categorization recall — "this merchant string resembles ones I previously tagged *Groceries*."
  - Q&A retrieval over past statements/notes.
  - Stores embeddings of transaction descriptions + user corrections; small, local.
- **Agent working memory / preferences.** A `user_corrections` and `preferences` table in SQLite
  (structured, auditable) — corrections also embedded into the vector store for fuzzy matching.
- **Why NOT a graph DB (Neo4j etc.):** the only "graph" relationships here (owner→account→institution,
  policy→beneficiary) are shallow foreign keys. A graph DB adds infra + a query language for near-zero
  benefit. If a genuinely relationship-heavy feature appears later (e.g. money-flow tracing across
  accounts), revisit — but do not pay that cost up front.

**Rule of thumb baked into the plan:** numbers & facts → SQLite; fuzzy similarity → vectors;
relationships → foreign keys until proven otherwise.

---

## 2a. Incremental ingestion — idempotency & temporal handling

Statements are **not** submitted as one batch. The user drops files into `data/inbox/` whenever they
arrive and runs `setu ingest` out-of-turn; each statement is an independent unit that appends to the
shared SQLite ledger, and the next `setu report` recomputes over whatever the ledger now holds. Batch
parallelism (§3a) is an optimization when several arrive together, never a requirement. Three
correctness rules make out-of-turn ingestion safe:

- **Statement-level idempotency (skip already-processed docs).** The `statements` table records a
  **`file_hash`** (SHA-256 of the raw file) plus a **uniqueness constraint on `(institution,
  account, period_end)`**. IngestionAgent's *first* step is a hash lookup: a seen hash is **skipped**
  with a log line, not reprocessed — so re-running `setu ingest data/*` is idempotent and can never
  double-count. The constraint also catches the same period arriving as a differently-named file.
  (This complements, at a coarser grain, the holding/transaction dedup already done in reconciliation.)
- **Temporal validity — latest snapshot per account wins.** Every balance/holding carries an
  **`as_of_date`** (the statement's `period_end`). A statement is a *point-in-time snapshot*, so
  `report`/`calc` value each account from its **latest** `as_of_date`, never by summing successive
  snapshots of the same account — otherwise a March statement ($214k) and a stale January one ($180k)
  would both count. Older statements are retained (history/audit) but not summed. `as_of_date` is a
  first-class column, and output validation (§3b) already range-checks that dates are plausible.
- **FX as-of policy (stated deliberately).** The MVP reports a **current net-worth snapshot**, so
  `fx` converts every holding at *today's* rate for a single consistent base-currency view. Converting
  each holding at its own statement-date rate (a historically faithful snapshot) is a later option; the
  point is the choice is explicit, not accidental — mixing the two silently would corrupt the total.

Net effect: adding documents incrementally, re-adding the same document, and adding an out-of-date
document are all handled deterministically — reinforcing the "every number is traceable and never
double-counted" guarantee.

---

## 3. Mapping to the six graded CMU concepts

The rubric grades six concepts. Each is designed into the architecture below with an explicit
demo/success-metric hook — this is what the final report and presentation are scored on.

| # | Concept | Where it lives in Setu | Success-metric demo |
|---|---|---|---|
| 1 | **Tool Calling** | The deterministic tools in `tools/` (pdf_extract, fx, calc, reconcile, categorize, reminders) exposed as callable functions; agent parses each tool's output and decides the next step. | Show the agent invoking a tool, reading the JSON result, and acting on it (e.g. `calc` returns net worth → agent reports it). |
| 2 | **Reasoning (ReAct / CoT)** | A **ReAct loop** drives the Q&A + analysis agent: Thought → Action (tool) → Observation → repeat, with visible traces. Recovers from missteps (wrong tool / bad parse → re-plans). | Ask "how much did I spend on insurance in INR last quarter?"; show the thought/action/observation trace and a recovery after a failed first attempt. |
| 3 | **Knowledge & Memory (RAG)** | **Retrieval-based memory** over three stores: (a) past task executions / run history, (b) parsing & API documentation for statement formats, (c) user corrections. Retrieved into context before acting. | Agent recalls "last time a Tata policy statement looked like this, the premium field was here" from the doc/execution store. |
| 4 | **Further Reasoning (Tree of Thought)** | **ToT** applied where the solution space branches: (a) reconciliation-strategy selection when totals mismatch (try multiple parse hypotheses, score each against the stated balance, keep the best), (b) forecasting extension (branch on scenarios). | Show the agent generating N candidate reconciliations, evaluating each, and selecting the one that balances. |
| 5 | **Multi-agent Coordination** | An **orchestrator** delegates to specialized sub-agents that can run in parallel: `IngestionAgent`, `ReconciliationAgent`, `InsightsAgent` (+ extension `ForecastAgent`). Independent statements ingest concurrently. | Demonstrate ≥1 specialized agent executing a task on the orchestrator's behalf; ideally 3 statements ingesting in parallel. |
| 6 | **Safety / Guardrails** | A dedicated **guardrail layer** (see §3b): read-only by default, no autonomous money movement, human-in-the-loop confirmation for any outward action, PII redaction before cloud calls, output validation. | Provide the written statement of potential unintended actions + the guardrails that block each. |

---

## 3a. Agent workflow — multi-agent + ReAct + ToT

**Orchestrator (ReAct planner)** receives a goal ("ingest this month's statements", "answer this
question", "what's due next?"), reasons about which specialized agent(s) to call, dispatches them
(in parallel where independent), observes results, and re-plans on failure.

```
                         ┌──────────────────────────────┐
                         │   Orchestrator (ReAct loop)   │
                         │  Thought → Action → Observe    │
                         └───────┬───────────┬───────────┘
              ┌──────────────────┘           └──────────────────┐
              ▼ (parallel per statement)                        ▼
     ┌──────────────────┐   ┌──────────────────┐      ┌──────────────────┐
     │  IngestionAgent  │   │ ReconciliationAgt│      │   InsightsAgent  │
     │ parse→extract→   │   │  ToT: N parse     │      │  RAG Q&A, net    │
     │ classify→dedup   │──▶│  hypotheses,      │──▶   │  worth, spend,   │
     │ (local model)    │   │  score vs stated  │      │  reminders       │
     └──────────────────┘   └────────┬─────────┘      └──────────────────┘
                                      │ (mismatch → re-parse / interrupt user)
                                      ▼
                              [ Guardrail layer §3b ]
```

- **Reconciliation is the primary feedback signal.** If summed transactions ≠ stated statement
  balance (within tolerance), the ReconciliationAgent uses **ToT** to try multiple parse hypotheses,
  scores each against the stated total, and either selects the balancing one or interrupts the user.
- **ReAct recovery:** when a tool fails or a parse is low-confidence, the agent records the
  observation and re-plans (different tool, re-parse, or ask user) rather than crashing — directly
  hitting the "recover from missteps" success metric.
- **Confidence thresholds** route low-confidence items to a human-in-the-loop node (LangGraph
  `interrupt`).
- **Memory (RAG):** before acting, agents retrieve relevant past executions + parsing/API docs +
  user corrections from the vector store.
- LangGraph **checkpointer** (SQLite-backed) gives durable, resumable, stateful multi-step runs (§3a-i).

### 3a-i. How the graph is built and run (`graph/build.py` + the SQLite checkpointer)

LangGraph models the agent as a **state machine**: a graph of **nodes** (functions wrapping an
agent/tool) connected by **edges**, all operating on one shared **State** (`graph/state.py`, a
`TypedDict` — this *is* working memory). `graph/build.py` is run once to assemble and compile it:

1. **Register nodes** — `ingest`, `reconcile`, `persist`, `ask_user`, `insights` (each wraps an agent
   or tool from `nodes.py`; a node takes State, returns a partial update LangGraph merges in).
2. **Wire edges** — normal edges for the linear path; a **conditional edge** after `reconcile` is where
   the ToT branch lives as control flow: a router reads the reconciliation score in State and returns
   `ok → persist` / `mismatch → ask_user` / `retry → reconcile`. That conditional edge *is* the
   "self-correcting pipeline."
3. **Compile with the checkpointer + interrupts** —
   `graph.compile(checkpointer=SqliteSaver(...), interrupt_before=["ask_user"])`.

`cli.py` then invokes the compiled graph per command with a `thread_id`.

**The SQLite checkpointer** snapshots State after every node, keyed by `thread_id`. One mechanism, four
payoffs Setu needs:
- **Durability/resumability** — crash or Ctrl-C mid-ingest → re-invoke with the same `thread_id`
  resumes from the last checkpoint; finished statements aren't redone.
- **Human-in-the-loop** — `interrupt_before=["ask_user"]` pauses *and persists* the run; `invoke`
  returns with State frozen in `setu.db`. The user answers hours later; `invoke(Command(resume=...))`
  continues exactly where it stopped. Without the checkpointer a paused run would lose working memory —
  this is what makes the reconciliation interrupt and ProfilingAgent elicitation possible.
- **Conversation continuity** — reusing a `thread_id` across `setu ask` calls retains prior context =
  short-term memory, no extra code.
- **Audit/time-travel** — the per-step State history reinforces the provenance guardrail (§3b).

**Two distinct SQLite roles (don't conflate):** the **checkpointer DB** holds *run/conversation state*
(working + short-term memory); the **ledger DB** (§2) holds *financial truth* (long-term memory). Same
engine, different jobs. This is the concrete mechanism behind the memory-type mapping in
`DESIGN_personas_memory.md` (working = State · short-term = checkpointer · long-term = ledger + vectors).

## 3b. Safety & guardrails (graded concept #6)

Setu is **read-and-advise by default** — it never moves money. The written safety statement for the
report enumerates:

- **Potential unintended actions:** mis-categorizing a payment; hallucinating a balance or due date;
  leaking account numbers/PII to a cloud LLM; acting on a misread statement; sending a reminder for a
  non-existent obligation; (extension) placing a trade or payment.
- **Guardrails that address each:**
  - **No autonomous outward actions** — money movement / trades are out of scope for the MVP; any
    such extension is gated behind explicit human confirmation.
  - **Human-in-the-loop confirmation** for every low-confidence extraction and any outward-facing
    action (e.g. writing a calendar reminder).
  - **PII redaction boundary** — raw account numbers only reach the *local* model; Claude payloads
    are redacted (verified in the privacy check).
  - **Deterministic-math guarantee** — no LLM computes balances; reconciliation must pass before any
    number is surfaced, so hallucinated figures cannot reach the user.
  - **Output validation** — schema/range checks on extracted values (dates plausible, amounts
    non-absurd, currencies known) before they enter the ledger.
  - **Full audit trail** — every tool call, agent decision, and correction is logged for review.

---

## 4. Code structure

```
setu/
├── config.yaml                 # model_router, base_currency, paths, thresholds
├── pyproject.toml
├── README.md
├── data/
│   ├── synthetic/              # generated/anonymized sample statements (checked in)
│   ├── inbox/                  # drop real statements here (gitignored)
│   └── setu.db                 # SQLite (gitignored)
├── setu/
│   ├── config.py               # load config, model router
│   ├── models/                 # SQLAlchemy ORM: Account, Holding, PolicyValue, Balance, Obligation,
│   │                           #   FxRate, RiskProfile (target allocation); Transaction (secondary);
│   │                           #   Statement (file_hash + as_of_date, §2a)
│   ├── db.py                   # session, migrations, dedup helpers (statement hash + latest-per-account)
│   ├── llm/
│   │   ├── router.py           # picks local vs Claude per stage from config
│   │   ├── claude.py           # Claude Agent SDK / API client wrapper
│   │   └── local.py            # Ollama client (extraction + embeddings)
│   ├── tools/                  # DETERMINISTIC tools the agent calls
│   │   ├── pdf_extract.py      # PDF/CSV → raw text/tables (pdfplumber/camelot)
│   │   ├── cas_parse.py        # Indian MF CAS (CAMS/KFintech) → holdings; wraps casparser (§4a)
│   │   ├── fx.py               # FX lookup (static table now; API later)
│   │   ├── calc.py             # net worth, allocation %, exposures (exact math)
│   │   ├── risk.py             # actual-vs-target allocation, concentration, drift (§0.4); quant metrics via quantstats (§4a)
│   │   ├── reconcile.py        # totals vs statement, discrepancy report
│   │   ├── policy_value.py     # picks the asset-value figure per policy type (see §5b)
│   │   ├── categorize.py       # (supporting) light cash-flow/savings signal only
│   │   └── reminders.py        # obligation/commitment detection, due dates, calendar/ICS
│   ├── knowledge/
│   │   └── policy_rules.yaml   # policy-type semantics KB (term/endowment/ULIP) for RAG (§5b)
│   ├── memory/
│   │   ├── vectorstore.py      # RAG: embed + recall (past runs, parsing/API docs, corrections)
│   │   ├── run_history.py      # logs past task executions for retrieval
│   │   └── preferences.py      # user corrections, learned prefs
│   ├── agents/                 # multi-agent coordination (concept #5)
│   │   ├── orchestrator.py     # ReAct planner: delegates + re-plans (concepts #2, #5)
│   │   ├── ingestion_agent.py  # parse→extract→classify→dedup
│   │   ├── reconciliation_agent.py  # ToT parse-hypothesis scoring (concept #4)
│   │   ├── insights_agent.py   # RAG Q&A: net worth, allocation, risk vs target (§0), reminders
│   │   └── forecast_agent.py   # (extension) news/market forecasting
│   ├── safety/
│   │   └── guardrails.py       # PII redaction, output validation, action gating (concept #6)
│   ├── graph/
│   │   ├── state.py            # LangGraph State schema (TypedDict)
│   │   ├── nodes.py            # node fns wrapping agents + tools
│   │   └── build.py            # assemble graph, checkpointer, interrupts, parallel branches
│   ├── cli.py                  # typer/click: ingest, ask, report, reminders
│   ├── events/
│   │   └── bus.py              # event bus: agents publish thought/action/observation/ask_user
│   └── dashboard/              # "Agent Feed + artifact tiles" UI (§8)
│       ├── server.py           # FastAPI + WebSocket: pushes agent events to the browser
│       ├── static/             # tiling grid front-end (tiles + live feed rail)
│       └── tiles.py            # tile renderers: net worth, allocation, risk-vs-target, holdings
└── tests/
    ├── test_reconcile.py       # golden synthetic statements → known totals
    ├── test_categorize.py
    └── test_fx_calc.py
```

Reusable/off-the-shelf building blocks (don't hand-roll): `pdfplumber`/`camelot` (PDF tables),
`casparser` (Indian MF CAS parsing — see §4a), `quantstats` (risk metrics — see §4a),
`SQLAlchemy` (ORM/portability), `LangGraph` (orchestration + checkpointer), `Chroma` or `sqlite-vec`
(vectors), `Ollama` python client (local model + embeddings), `FastAPI` + WebSocket (live
agent-feed dashboard; `Streamlit` as a faster fallback), `pydantic` (structured extraction schemas),
`typer` (CLI).

---

## 4a. Reuse-first: proven libraries over hand-rolled parsing/math

A prior-art scan (see `DESIGN_prior_art.md`) confirmed two things: **(a)** no existing project occupies
Setu's cross-border US+India + deterministic-spine intersection, and **(b)** mature repos independently
adopt Setu's exact "LLM narrates, Python computes" principle (FinRobot: *"Numbers are code-calculated,
narratives are LLM-assisted"*; ai-berkshire: all math in `decimal.Decimal`). The actionable takeaway —
and a direct answer to the checkpoint-1 review's "don't rebuild what exists / add quant value" notes —
is to **wrap solved problems and spend effort on the differentiators.**

- **`casparser`** (codereverser, MIT) — parses Indian mutual-fund **Consolidated Account Statements**
  (CAMS/KFintech/NSDL/CDSL) into structured holdings + transactions, **entirely offline**. This is the
  single highest-leverage reuse: Indian CAS parsing is fiddly and fully solved, so `tools/cas_parse.py`
  is a thin wrapper, **not** a hand-rolled parser. Offline operation also satisfies the PII boundary
  (§3b) — statement contents never leave the machine. `pdf_extract.py` remains for US brokerage/bank
  PDFs and insurance statements, which `casparser` does not cover.
- **`quantstats`** — pure-Python risk/performance metrics (Sharpe, Sortino, max drawdown, VaR, CVaR,
  volatility). This is the concrete "Wall Street quant equations" layer the review asked for: `risk.py`
  calls `quantstats` for the metrics rather than re-deriving formulas, keeping the determinism guarantee
  (§1) intact — the LLM *explains* a Sharpe ratio, a library *computes* it.
- **`Riskfolio-Lib`** or `PyPortfolioOpt` (**post-MVP**) — portfolio optimization / efficient frontier /
  HRP, for a future "how should I rebalance?" answer. Deferred to §6b; noted here so the seam is known.
- **Deliberately avoided:** `pyfolio`/`empyrical` (legacy/unmaintained), `mlfinlab` (proprietary
  license), `QuantLib` (C++ derivatives-pricing overkill), a generic hand-rolled bank-statement parser,
  and any dependency on India's Account Aggregator for the MVP (nascent — revisit post-MVP, see §6b).
- **Anti-pattern explicitly rejected:** `gpt-investor`-style designs that let the LLM interpret/compute
  financial numbers directly — precisely the hallucination risk §1 and §3b forbid.

---

## 5. Environment, tools, data sources (maps to capstone bullets)

- **Documents:** synthetic **portfolio** statements (PDF/CSV) rich in *holdings* — brokerage &
  mutual-fund holdings with quantities/NAVs, 401k/IRA summaries, ULIP fund values, endowment
  surrender/maturity values, bank balances — in `data/synthetic/`.
- **User-declared input:** a **target risk profile** (asset-class / geography / currency targets)
  that drives the actual-vs-target feedback loop (§0.4).
- **Tools:** PDF/CSV extractor, FX lookup, deterministic calculator (net worth/allocation/exposure),
  **risk analyzer** (actual vs target, concentration), policy-value selector, reconciler,
  reminder/ICS generator, (extension) market-price + news fetch.
- **Data stores:** SQLite ledger (truth) + vector store (semantic).
- **Users:** single trusted individual — provides docs, sets a target risk profile, confirms
  low-confidence items, receives net-worth/allocation reports and risk feedback.

---

## 5b. How Setu understands insurance policies (valuation)

Insurance is modeled differently from stocks/funds because **a policy has no market price** — its
"value" must be *extracted or supplied*, never derived. The agent separates two things:

- **Semantics (what kind of value)** — comes from a small **knowledge base** (`knowledge/policy_rules.yaml`)
  retrieved via RAG. This is a graded "store of knowledge" (concept #3). It encodes the rules:

  | Policy type | Contributes to net worth? | Which figure = asset value |
  |---|---|---|
  | **Term** (pure protection, e.g. term plan) | No — coverage only | None; record *death benefit / sum assured* as protection, not an asset |
  | **Endowment / money-back** (classic LIC) | Yes | **Surrender value** today; **maturity value** + accrued **bonus** at term end |
  | **ULIP** (unit-linked, e.g. Tata) | Yes | **Fund value = units × current NAV** (market-linked) |

- **Numbers (the actual value)** — come **only** from the user's documents (annual policy statement,
  surrender-value quote, ULIP NAV statement) or from the user directly. The agent **never computes or
  guesses** a surrender/maturity value — these are non-derivable and prime hallucination risks, so the
  guardrail forbids it. If a figure isn't present, the agent marks it **unknown** and asks the user.

So the flow is: extract policy doc → **classify type** → look up the type's rule in the KB → pull the
right figure from the statement (or ask) → record as asset value or coverage accordingly. `policy_value.py`
implements this selection deterministically; the KB supplies the meaning; the documents supply the numbers.

---

## 6. 7-week roadmap

Each week is tagged with the graded concept(s) it delivers.

| Week | Deliverable | Concepts |
|---|---|---|
| 1 | Repo scaffold, `config.yaml`, SQLite schema/ORM (holdings/policy-values/balances/risk-profile centric), synthetic **portfolio** generator (US+India, USD+INR). | — |
| 2 | Deterministic **tools** (`pdf_extract`, `fx`, `calc` = net worth + allocation %) + local-model extraction of holdings; tool-calling wired up. | #1 Tool Calling |
| 3 | **Orchestrator ReAct loop** + `IngestionAgent`; LangGraph skeleton + SQLite checkpointer; visible thought/action/observation traces. | #2 Reasoning, #5 Multi-agent |
| 4 | **ReconciliationAgent with Tree-of-Thought** parse-hypothesis scoring + human-in-the-loop interrupts; policy-value selection (§5b); dedup. | #4 Further Reasoning |
| 5 | **RAG memory** (past runs + parsing docs + policy-rules KB + corrections); **`risk.py`: actual-vs-target allocation + concentration** (§0.3–0.4); parallel ingestion. | #3 Memory, #5 Multi-agent |
| 6 | **Guardrail layer** (PII redaction, output validation, action gating) + written safety statement; commitment reminders (ICS); Streamlit dashboard (net worth, allocation, risk-vs-target). | #6 Safety |
| 7 | InsightsAgent Q&A over portfolio ("am I over-concentrated in US tech?", "real INR exposure?"), polish, tests, **final report + presentation**. (Stretch: `ForecastAgent`.) | all |

**Deliverables (per CMU):** Final Report (problem, methodology, results, conclusions — structured
around the six concepts above) + formal Presentation for faculty and peers.

---

## 6b. Future work (post-capstone extensions)

Staged deliberately outside the MVP so the graded scope stays on synthetic data:

- **Live data:** brokerage APIs, live FX + market-price feeds (`yfinance` for the MVP-grade extension →
  `OpenBB` for a broader, MCP-native feed later), mutual-fund NAV lookup. **Plaid** is US/UK/EU only —
  do **not** assume it covers Indian accounts; Indian ingestion stays on manual CAS upload +
  `casparser` (§4a). India's **Account Aggregator** framework is the eventual consented-data path but is
  still nascent (no mature OSS), so it is explicitly *not* an MVP dependency.
- **Portfolio optimization:** `Riskfolio-Lib` / `PyPortfolioOpt` for efficient-frontier / rebalancing
  suggestions (builds on the `quantstats` metrics already in `risk.py`, §4a).
- **Forecasting:** `ForecastAgent` — news + market synthesis for holdings, with confidence + sources.
- **Scale/robustness:** Postgres migration, multi-user, richer dashboard.

### Live valuation — market-price tool + sector reference (`tools/price.py`)

The MVP values holdings at the figure **stated in the statement** (as of its date) — grounded, no
lookup needed. A live version needs current *value = quantity × current price*, and price is external
data no model knows. This is the **exact same shape as the existing `fx` tool** (LLM never knows the
number; a tool fetches it; `calc` multiplies deterministically), so it slots in without re-architecting:

- **`price` tool** — fetches current equity quotes (`yfinance` for the MVP-grade extension, `OpenBB`
  for a broader feed later) and **mutual-fund NAVs** for Indian funds; `calc` then computes
  `stored_quantity × fetched_price`.
- **Sector/industry reference** — concentration analysis ("am I over-concentrated in US tech?") needs
  a reliable **ticker → sector** mapping. The model's pre-trained recall is fine for well-known
  tickers but unreliable/stale for the rest, so sector is treated as a **lookup**, not model memory
  (static ticker→sector table for the MVP; a live reference feed as the extension). Geography and
  asset class remain model-classified (well inferable from statement context) and user-correctable.

### Tax guidance & cross-border strategy (`knowledge/tax_rules.yaml` + `tools/tax.py`)

Arguably the highest-value extension for a US–India household, and modeled exactly like the
risk-advice loop: **RAG over a curated, *dated* tax-rules KB + deterministic calculation + an
"estimate & educate, never advise" scope.**

- **Why RAG, not model memory:** Indian investment-tax rules (LTCG/STCG, indexation, the equity
  exemption threshold, ELSS deductions, TDS on NRI holdings) and **US–India cross-border rules**
  (DTAA foreign-tax-credit, FBAR reporting, PFIC treatment of Indian mutual funds held by US persons)
  are public but **change yearly** — stale/hallucinated tax numbers are dangerous. Rules live in a
  sourced, dated KB the model *applies*; it never invents a rate or threshold.
- **Numbers stay deterministic:** a tax *estimate* = `tools/tax.py` applying a retrieved rule to real
  holdings/lots; the LLM explains, never computes the figure.
- **Account type drives it:** the schema already tracks account type (taxable / 401k / IRA / demat /
  MF folio), which is *why* this is feasible — tax treatment keys off type. Enables "how much of my
  equity sits in tax-advantaged accounts?" and per-lot gain estimates.
- **Scope guardrail (sharper than for investments):** "here is your estimated LTCG exposure if you
  sold X, under this year's rule" (analysis) — **never** "you should sell to harvest losses" (regulated
  tax advice). Every output carries a prominent **"consult a tax professional"** disclaimer.

### Gmail ingestion + encrypted-statement handling (designed as a safety showcase)

Automatically fetching statements from email — including the password-protected PDFs Indian banks and
insurers send — is high-value but also the **highest-risk** surface in the system, so it is future
work and, when built, is framed as a demonstration of good guardrail engineering (reinforcing concept
#6) rather than a convenience hack.

**Flow:** `tools/gmail_fetch.py` searches Gmail (OAuth) for statement attachments
(`from:<institution> has:attachment filename:pdf`) → downloads to `data/inbox/` → the existing
pipeline takes over. Locked PDFs are decrypted **locally** with `pikepdf`/`pypdf`.

**OAuth flow (delegated, least-privilege access — never the user's Google password):**
- **One-time app registration:** a Google Cloud project with the Gmail API enabled yields a client
  ID + secret; the app declares its scopes and redirect URI up front.
- **Consent → token exchange:** the user authorizes *at Google* (not in Setu); Google returns a
  short-lived **access token** (~1 h) for API calls and a long-lived **refresh token** used to
  silently mint new access tokens without re-consenting.
- **Token storage:** the refresh token is a secret and gets the *same* treatment as PDF passwords —
  stored in the **OS keychain** (`keyring`), never in config, git, logs, or an LLM payload.

**Safety design (non-negotiable for this feature):**
- **Scoped OAuth — `gmail.readonly` only.** The agent can search + download attachments but *cannot*
  send, delete, or modify mail. Least privilege is enforced at the API level, not by convention, so a
  misbehaving agent or leaked token has a bounded blast radius. Revocable anytime from the user's
  Google account.
- **Passwords never live in code or config** — read from the OS keychain (macOS Keychain via
  `keyring`), one entry per institution. Never logged, never sent to any LLM.
- **Decryption is local only** — the LLM sees only the already-extracted, PII-redacted text, never the
  password or the raw encrypted file.
- **Human-in-the-loop gate** — the agent asks for explicit confirmation before accessing Gmail; it is
  read-only on the mailbox (search + download, never send/delete).
- **The consent is the *user's*, on the *user's* machine.** In the local/BYO-key model the buyer
  authorizes their own Google account and the refresh token stays in their keychain — the vendor never
  sees or custodies any user's email or token (unlike a hosted SaaS holding thousands of tokens).
- Reuses the Gmail tooling direction from the related [[project_personal-agent]] work.

**Production gate:** Google **verifies apps** requesting sensitive scopes (like Gmail) before public
use — a review, sometimes a security assessment. For the capstone this is avoidable by running in
OAuth "testing" mode with the developer's own account; a real multi-user product must budget for this
verification (potentially lengthy) before launch.

Note for the capstone: the *password-handling flow* can be demonstrated safely now using a synthetic
locked PDF with a throwaway password, proving the mechanism without touching real credentials or a
real mailbox.

---

## 7. Verification

- **Golden-file tests:** each synthetic statement ships with known correct totals; `test_reconcile.py`
  asserts computed net worth / per-account balances match exactly (proves LLMs aren't doing math).
- **End-to-end demo:** `setu ingest data/synthetic/*` → `setu report` shows a currency-normalized
  **net-worth + asset-allocation** view (by class, geography, currency); `setu ask "am I
  over-concentrated in US tech?"` / `"what's my real INR exposure?"` / `"how far is my allocation
  from my target?"`; dashboard renders the same. Corrupt one statement's total → confirm the
  reconciliation loop detects the mismatch and interrupts for the user.
- **Risk-alignment check:** set a target profile, confirm `risk.py` reports actual-vs-target drift
  and the agent explains it.
- **Learning check:** correct a mis-classified holding/policy, re-run a similar one, confirm the
  correction is recalled from the vector store/preferences.
- **Privacy check:** run with cloud calls logged; confirm raw account numbers only appear in
  local-model calls, never in Claude payloads (redaction verified).

---

## 8. UI & interaction pattern — "Agent Feed + artifact tiles"

Inspired by the *RocketSmith* sample shown in class: a clean, tiling **grid of resizable artifact
panels** alongside a live **Agent Feed**. This is both a UI choice and an *architectural* choice —
the agent's work is made observable, not hidden behind a spinner.

**Layout (borrowed pattern, adapted to wealth):**

```
┌──────────────┬───────────────────────────────────────────────┬──────────────────┐
│ SIDEBAR      │  ARTIFACT TILES (resizable grid)              │  AGENT FEED       │
│              │  ┌───────────────┐ ┌───────────────────────┐  │  ▸ Thought: need  │
│ Setu  v0.x   │  │ NET WORTH     │ │ ASSET ALLOCATION      │  │    FX rate...     │
│ • Agent Feed │  │ $ / ₹ tile    │ │ donut: eq/debt/cash   │  │  ▸ Action: fx()   │
│ • Portfolio  │  └───────────────┘ └───────────────────────┘  │  ▸ Observed: 83.1 │
│ • Allocation │  ┌───────────────┐ ┌───────────────────────┐  │  ▸ Reconciled ✓   │
│ • Risk       │  │ RISK vs TARGET│ │ HOLDINGS / POLICIES   │  │  ▸ Ask user: is   │
│ • Holdings   │  │ drift bars    │ │ table, US+India       │  │    this ULIP...?  │
│ • Reminders  │  └───────────────┘ └───────────────────────┘  │                   │
└──────────────┴───────────────────────────────────────────────┴──────────────────┘
```

- **Tiles = artifacts.** Each panel renders one wealth artifact: **Net Worth**, **Asset Allocation**
  (by class / geography / currency), **Risk vs Target** (drift bars, §0.4), **Holdings & Policies**
  table, **Reminders/Commitments**. Tiles are resizable; layout is resettable — the RocketSmith
  "blocks on a grid" feel, with clean monospace/technical typography.
- **Agent Feed = live ReAct trace, pushed over WebSocket.** Like RocketSmith, the agent streams
  events to the UI over a **WebSocket** (server → client push) rather than request/response polling.
  The orchestrator emits structured events — `thought`, `action`, `observation`, `reconciled`,
  `tot_hypothesis`, `ask_user`, `artifact_updated` — as it runs; the right rail renders them live and
  tiles re-render the instant their underlying artifact changes. This directly surfaces the graded
  reasoning loop (concept #2) and makes multi-agent activity (concept #5) visible as it happens.
- **Why WebSocket (the architectural point):** agent runs are long and multi-step, so a pushed event
  stream (not a blocking call that returns only the final answer) is what makes the work observable
  and lets human-in-the-loop `ask_user` prompts appear mid-run and unblock the agent on reply. Event
  emission decouples cleanly from the LangGraph nodes — each node/agent just publishes events to a bus
  the WebSocket layer forwards.
- **Inspectable, like RocketSmith's Source/Model/GCode tabs:** a holding tile can flip between
  **Value / Source-statement / Reasoning** — showing the number, the statement line it came from, and
  how the agent classified/valued it. This reinforces the "never hallucinate a number" guardrail by
  making provenance visible.
- **Interaction:** questions typed in the feed (or CLI) trigger a run; the answer updates the relevant
  tile *and* logs its reasoning in the feed — so the user sees both the result and the how.

**Tech:** the WebSocket feed is best served by **FastAPI** (native WebSocket support) with a small
static front-end — this reproduces RocketSmith's live-push model directly. A **Streamlit** build is
the faster fallback (its auto-rerun / `st.fragment` polling *approximates* live updates but is not
true server push), acceptable if front-end time is short. Recommended MVP: **FastAPI + WebSocket +
a lightweight vanilla/React grid**; upgrade to a real tiling window manager (`react-mosaic` /
`dockview`) for RocketSmith-grade polish as future work (§6b). Either way the event bus is the same;
only the transport differs.

**Architectural takeaway from RocketSmith:** treat every agent output as a *named, inspectable
artifact* with visible provenance and a live activity feed — not opaque chat. Setu adopts this: the
ledger, allocation, risk report, and each answer are artifacts the user can open, trace, and correct.
