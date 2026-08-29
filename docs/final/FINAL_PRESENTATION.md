# Setu Final Presentation

**Format:** 10 slides, approximately 9 minutes 15 seconds  
**Audience:** Technical reviewers for the CMU Agentic AI capstone  
**Central takeaway:** Setu is useful because it separates probabilistic document interpretation from
deterministic financial truth and sends uncertainty to the user instead of hiding it.

## Slide 1 - Setu: A Local-First Cross-Border Wealth Agent

**Visible copy**

- US + India financial documents
- Local interpretation, exact calculations, human control
- CMU Agentic AI Capstone

**Visual direction:** Minimal title slide with a simple bridge motif joining US and India source
documents to one portfolio view.

**Speaker notes - 0:30**

Setu is a local-first agent for someone who holds assets in both the United States and India. It
reads several kinds of financial documents, creates one source-backed ledger, and explains the
portfolio's value, return, risk, and missing information. The main design idea is simple: models
interpret irregular documents, deterministic code protects financial truth, and the user resolves
uncertainty.

[Sources: `ARCHITECTURE.md`]

## Slide 2 - Financial truth is split across countries and products

**Visible copy**

- Statements use different currencies, layouts, and labels.
- Insurance coverage, premiums, maturity, and current value mean different things.
- One bad extraction can distort net worth and every later recommendation.

**Visual direction:** Three heterogeneous documents - US brokerage, Indian bank, insurance policy -
converging toward one incomplete portfolio view.

**Speaker notes - 0:50**

A cross-border investor may have a US brokerage account, a 401(k), Indian mutual funds and cash, and
LIC or ULIP policies. A normal tracker often misses the evidence behind those values. Insurance is a
particularly important example: ten million rupees of term coverage is protection, not a ten-million-
rupee asset. An endowment policy can be valid even when the current surrender value is absent. If an
agent confuses these ideas, the portfolio can look much richer than it really is. Setu addresses both
data fragmentation and the reliability of the resulting financial view.

[Sources: `ARCHITECTURE.md`, `SYNTHETIC_DEMO_SCENARIO.md`]

## Slide 3 - The goal is grounded understanding, not autonomous action

**Visible copy**

**Setu does**

- Ingest investments, bank balances, and insurance policies
- Normalize USD and INR values with source provenance
- Calculate net worth, ROI, allocation, liquidity, and risk signals
- Explain results and surface missing evidence

**Setu does not**

- Trade, move money, predict markets, or invent unsupported values

**Visual direction:** One clear left-to-right flow from documents to a portfolio diagnosis, with the
out-of-scope actions shown beyond a hard boundary.

**Speaker notes - 0:45**

The system's goal is not to become an autonomous financial adviser. It turns supported PDFs into a
normalized ledger and helps the user understand what is known, what it means, and what is missing.
The final capstone scope includes source-backed ROI, concentration, currency exposure, known premium
commitments, and an explainable health diagnostic. It deliberately excludes outward financial
actions and personalized tax or market advice. That boundary made the system testable and reduced
the impact of a model mistake.

[Sources: `ARCHITECTURE.md`]

## Slide 4 - Models interpret; code verifies; humans decide

**Visible copy**

```text
PDF -> local extraction -> typed state -> reconciliation -> ledger -> exact tools -> dashboard
                                      | mismatch |
                                      +-> human review

Typed question -> identifier masking -> bounded Claude tool loop -> grounded explanation
```

**Visual direction:** The deck's one architecture diagram. Use two horizontal paths: the local
ingestion graph on top and the separate Claude explanation loop below. Emphasize the ledger and
deterministic tools between them.

**Speaker notes - 1:10**

Setu has two related but separate paths. The ingestion path is a LangGraph state machine. PDF text is
read locally, and optional OCR is used only when embedded text is missing. Bank balances use a
deterministic parser; holdings and policies can use qwen2.5 through local Ollama to produce typed
records. The reconciliation role independently checks stated totals and evidence. A valid result is
persisted idempotently. A mismatch retries once and then pauses for a human decision.

The second path is Ask Setu. Claude cannot read a PDF or write to the ledger. It can call only three
read-only tools for FX, net worth, and portfolio analysis. Python and SQL calculate the answer, and
Claude explains the returned JSON. The components communicate through typed LangGraph state and tool
results, not free-form agent conversations. This gives Setu role separation without using CrewAI.

[Sources: `ARCHITECTURE.md`]

## Slide 5 - Every displayed value remains tied to evidence

**Visible copy**

1. Classify the document and extract only supported fields.
2. Validate schemas, totals, currency, and policy evidence.
3. Persist with file hash, statement period, and source date.
4. Calculate from the latest active source for each account.
5. Pause when the evidence cannot support a safe value.

**Visual direction:** A five-stage process with a visible review branch at validation and a reversible
source switch at calculation.

**Speaker notes - 0:50**

Provenance is not just an audit column. Every persisted value keeps its statement and date. Duplicate
files and repeated statement periods cannot silently increase net worth. The current portfolio uses
the latest active snapshot for each account. In the dashboard, the user can deactivate a document;
all holdings, balances, policies, and obligations linked to that source immediately leave the
calculation without being deleted. Reactivating it restores the evidence. This gives the user direct
control over the dataset behind the answer.

[Sources: `ARCHITECTURE.md`, `README.md`]

## Slide 6 - Implementation failures made the design smaller and safer

**Visible copy**

| Early direction | Final decision |
|---|---|
| General LLM financial assistant | Local interpretation + deterministic financial spine |
| One generic statement extractor | Separate holdings, bank, and policy handling |
| RAG for safety-critical policy rules | Versioned rules; retrieval deferred |
| Full Tree of Thought and CrewAI | Bounded hypotheses in LangGraph |
| Five broad agents | Fewer active, permission-scoped roles |

**Visual direction:** A clean before-and-after comparison, not a dense architecture table.

**Speaker notes - 0:55**

The design changed when realistic documents failed. A generic holdings extractor could not safely
represent a bank certificate or distinguish insurance coverage from value. The final design uses
document-specific handling over one ledger. I also chose not to implement the planned vector store
for policy rules. The rule set was small, and semantic retrieval could select a plausible but wrong
policy rule. Full Tree of Thought and a generator-critic crew were also more complex than the problem
required. A bounded set of total hypotheses, ranked by source authority, preserved structured
reasoning while remaining reproducible. These are deliberate architecture decisions, not missing
labels on existing features.

[Sources: `DESIGN_EVOLUTION.md`]

## Slide 7 - Demo: six documents reveal more than net worth

**Visible copy**

```text
Seed synthetic portfolio -> inspect evidence -> review risks -> deactivate one source
```

- Net worth: **$275,488.50**
- Document-backed investment ROI: **43.21%**
- Health diagnostic: **37/100 - Needs attention**
- One LIC current-value gap remains explicitly unknown

**Visual direction:** Use a real dashboard screenshot with the four figures annotated lightly.

**Speaker notes - 1:50 including live demo**

I will start from the reproducible synthetic demo rather than personal data. It contains six source
documents: US brokerage and retirement statements, Indian mutual funds and cash, Tata AIA insurance,
and an LIC policy. The dashboard calculates $275,488.50 of net worth. It includes the ULIP's stated
fund value, excludes term coverage, and keeps the LIC current value unknown because no surrender value
is stated.

The investment view shows $262,135.20 of current investment value against $183,045 of source-stated
cost, producing 43.21% ROI. I will open the attention area to show that the 37/100 result is composed
from target alignment, concentration, currency, liquidity, and data completeness. Then I will open
Data sources and deactivate one statement. The linked records disappear from portfolio calculations
and return when I reactivate it. This demonstrates that retrieval of a number is not the endpoint:
Setu preserves evidence, exposes uncertainty, and gives the user control over the active dataset.

[Sources: `SYNTHETIC_DEMO_SCENARIO.md`, `FINAL_DEMO.md`]

## Slide 8 - The portfolio needs attention for different reasons

**Visible copy**

- **85.0% equity** - long-term allocation skew
- **30.3% Apple** - single-position concentration
- **87.1% USD** - above the declared 60% guardrail
- **76.2%** - cash coverage of known annual premiums
- **Current, short-term, and long-term risk: elevated**

**Visual direction:** One large 37/100 health dial or score at left, with four horizontal evidence
bars and a short label at right. Avoid a grid of dashboard cards.

**Speaker notes - 0:50**

These signals show why Setu adds more value than an asset inventory. The portfolio is equity-heavy,
one stock is highly concentrated, USD exposure exceeds the user's declared currency guardrail, and
known cash does not cover all annual policy premiums. Current risk, short-term liquidity risk, and
long-term allocation risk are all elevated for different reasons. The score is deterministic and
each component is visible. It is a diagnostic, not a market forecast or investment instruction, so
the suggestions focus on questions to review and missing evidence rather than naming a trade.

[Sources: `SYNTHETIC_DEMO_SCENARIO.md`]

## Slide 9 - Evaluation supports specific, bounded claims

**Visible copy**

- **6/6** document classifications
- **4/4** golden reconciliations
- **7/7** live holding and cost-basis extractions
- **0** net-worth error and unsafe term valuations
- **110** regression tests passed
- **0** raw-document tools exposed to Claude

**Footer:** Synthetic baseline; not a claim of accuracy across every institution or PDF layout.

**Visual direction:** A single evidence ladder from classification to privacy, with the corpus-size
caveat visually attached to the results.

**Speaker notes - 1:00**

I evaluated the claims against a known synthetic corpus. The final live Ollama run classified all six
documents, passed four golden reconciliations, and recovered all seven investment positions with
their cost basis. A planted mismatch triggered human review. Net worth matched independently
generated ground truth exactly, term coverage never entered wealth, all three risk horizons were
evaluated, and Claude's registry contained no raw-document tool. The full regression suite passed 110
tests.

The limitation is important: six generated documents do not prove general extraction accuracy. OCR
logic is tested, but the final recorded run did not use a broad scanned-image benchmark. These results
establish a repeatable baseline and safe-failure behavior, not universal document support.

[Sources: `docs/EVALUATION.md`, `docs/evaluation/final-evaluation.json`]

## Slide 10 - A reliable agent is a controlled system, not just a prompt

**Visible copy**

- Probabilistic models interpret and explain.
- Deterministic tools own financial truth.
- Human review owns unresolved evidence.

**Repository:** github.com/gadodia/Setu  
**Next:** broader anonymized corpus, dated market data, goals and liabilities, cited public retrieval

**Visual direction:** Resolve the bridge motif from slide 1, now showing documents, controls, and a
grounded decision view connected end to end.

**Speaker notes - 0:35**

Setu's main strength is not that an LLM can read a statement. It is the control system around that
model: local processing, typed state, exact calculations, provenance, bounded tools, and human review.
Its current limits are explicit, and the next work is to broaden evidence before adding autonomy. The
public repository contains the code, architecture, synthetic demo, evaluation artifact, tests, and
review instructions. My central lesson is that dependable agents come from clear boundaries between
interpretation, truth, and action.

[Sources: `ARCHITECTURE.md`, `README.md`]
