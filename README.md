# Setu (सेतु)

> Sanskrit/Hindi for **"bridge."** Setu bridges an individual's finances across the **US and India**
> into one clear view.

Setu is a cross-border **wealth & portfolio agent** (CMU Agentic AI capstone). It consolidates one
person's assets scattered across US and Indian institutions — brokerage & retirement accounts, Indian
mutual funds, bank balances, and insurance policies (LIC, ULIP, endowments) — across currencies and
incompatible statement formats into a single **net-worth, source-backed ROI, asset-allocation, and
risk-vs-target** view.

**Design principle:** models interpret, deterministic code verifies and calculates, and humans
resolve uncertainty. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the implemented design and its
boundaries.

## Status

The final capstone slice is working: SQLite ledger, reproducible synthetic US/India statements,
deterministic `calc`/`fx` tools, local-model extraction, an authenticated FastAPI dashboard, and a
checkpointed LangGraph ingestion flow with reconciliation and human review. Insurance PDFs are
routed separately: TERM is recorded as coverage with no asset value, endowment uses only a stated
current surrender value, and ULIP uses only a stated current fund value. Missing current values fail
closed instead of being guessed.

Scanned/image-only pages use the optional local PaddleOCR-VL fallback. Premium obligations are
created when the document includes a premium amount; common ISO, `DD-Mon-YYYY`, and Indian
`DD/MM/YYYY` due-date formats are supported.
Policy extraction runs locally, and raw policy text is not copied into durable LangGraph checkpoints;
the ledger receives only validated structured fields. Clearly labelled policy fields are parsed
deterministically and override missing or conflicting local-model output. Document routing and key
policy semantics are also checked deterministically. Policy identifiers are masked before
persistence.

Bank statements use a dedicated deterministic balance path, so an HDFC closing balance is not
mistaken for an empty holdings statement. Investment statements can retain an explicit cost basis
or invested amount. Setu calculates unrealized gain and ROI only for covered positions and reports
the coverage ratio; missing cost remains unknown. The dashboard also surfaces current, short-term,
and long-term risk; an explainable five-part health score; concentration, currency exposure,
allocation drift, liquidity, source freshness, valuation gaps, and bounded review suggestions.
Claude Q&A receives only sanitized ledger calculations—never raw PDFs, extracted document text, or
file paths.

The final MVP does **not** implement stock research, form filling, semantic RAG, a CrewAI team, or
autonomous trading. Those are future extensions. The architecture document distinguishes early
checkpoint plans from the components that run today.

## Reviewer quickstart

The seeded demo does not require a cloud key or a running local model. It creates a separate
`data/setu-demo.db` and does not modify `data/setu.db`.

```bash
uv sync
cp .env.example .env
```

Set a unique dashboard password of at least 12 characters in the gitignored `.env` file:

```dotenv
SETU_DASHBOARD_PASSWORD="replace-with-your-own-long-password"
```

```bash
uv run setu demo --reset
```

Open `http://127.0.0.1:8765`. The expected synthetic view has net worth **$275,488.50**, seven
cost-backed investments, three policies, three premium obligations, and an explainable health score
of **37/100**. See [`SYNTHETIC_DEMO_SCENARIO.md`](SYNTHETIC_DEMO_SCENARIO.md) for every planted risk
and expected figure.

## Optional live features

To ingest a new text-based statement with the local model:

```bash
ollama serve
ollama pull qwen2.5:7b
uv run setu ingest path/to/synthetic-statement.pdf
```

Install the larger optional OCR stack only for scanned/image-only pages:

```bash
uv sync --extra ocr
```

Ask Setu additionally requires an Anthropic API key in the project-local `.env`. The key is sent
only to Anthropic's official API endpoint; it is never needed for the seeded dashboard, exact
calculations, or offline evaluation.

## Evaluation

```bash
uv run setu evaluate               # deterministic synthetic checks
uv run setu evaluate --live-model  # also checks Ollama extraction
uv run pytest -q                   # full regression suite
```

The current baseline is 110 passing tests. The evaluation corpus has 6/6 document classifications,
4/4 golden reconciliations, exact synthetic net worth, 7/7 cost-basis coverage, no unsafe term
valuation, explicit mismatch escalation, and no raw-document cloud tool. These results describe the
included synthetic corpus, not every possible institution or PDF layout.

The dashboard fails closed when no password is configured. Its login session is held only in the
running Setu process, expires after eight hours, and is cleared whenever the server restarts. The
browser receives an HTTP-only, same-site session cookie; repeated incorrect logins are temporarily
rate-limited. Dashboard pages, APIs, data-source controls, uploads, review decisions, and the live
activity connection all require authentication. Setu still binds only to `127.0.0.1`; the password
is an additional local access boundary, not a reason to expose the development server publicly.

In the dashboard, choose **Import document** to add a PDF statement or insurance policy. Setu
detects the document type, processes it through the existing LangGraph ingestion flow, and updates
the dashboard after validated data reaches the ledger. Reconciliation mismatches pause in the
Review queue for an explicit accept or reject decision. Uploads are limited to 25 MB and their
temporary PDF files are removed after processing.

The **Data sources** section lists each imported statement and shows whether it is active and
currently used in the portfolio. Turning a source off is reversible: Setu retains its validated
records and provenance but excludes every linked holding, balance, policy value, policy contract,
premium obligation, and transaction from portfolio views and calculations. If a newer statement is
disabled, the previous active snapshot for that account can become current again. Legacy or
synthetic rows that are not linked to a source document are identified separately and remain active.

The **Insurance policies** section shows coverage, current asset value, premium information,
valuation basis, maturity evidence, source document, and validation status. Premium notices and
receipts are accepted as partial policy evidence: they can establish coverage and premium facts,
but an absent surrender/fund value remains unknown and is excluded from current net worth. Setu
shows maturity amounts transcribed from a policy document, official benefit illustrations, or a
narrow source-backed product rule such as LIC Money Back Plan 75. It shows each component and its
assumptions; it does not compound premiums or invent future bonuses.

The **Investment performance** section compares current value with source-stated cost basis and
shows unrealized gain, ROI, and evidence coverage. It deliberately excludes cash, insurance,
taxes, fees, and distributions. **What needs attention** ranks deterministic observations such as
position concentration, USD exposure against the configured guardrail, and allocation drift. Use
**Ask Setu** for a plain-language explanation of those sanitized results; an Anthropic API key in
the project-local `.env` is required for that optional cloud step. Answers use a safe,
readable Markdown layout with a direct answer, grounded evidence, watch-outs, and data limits when
relevant. `config.yaml` bounds each Claude turn to 1,200 output tokens and the tool loop to four
rounds; the UI explicitly warns if an answer reaches that limit instead of silently cutting it off.

## Docs

`SUBMISSION_checkpoint1.md` through `SUBMISSION_checkpoint6.md` are historical design snapshots.
They intentionally preserve ideas considered at each stage; [`ARCHITECTURE.md`](ARCHITECTURE.md) is
the authoritative description of the final runtime.

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — implemented design, decisions, code map, and limitations.
- [`DESIGN_EVOLUTION.md`](DESIGN_EVOLUTION.md) — how the initial checkpoint plans became the final
  bounded architecture.
- [`DESIGN_personas_memory.md`](DESIGN_personas_memory.md) — early persona and memory design artifact.
- [`DESIGN_prior_art.md`](DESIGN_prior_art.md) — early competitive landscape and reuse decisions.
- [`SETU_ARCHITECTURE_INTERVIEW_GUIDE.md`](SETU_ARCHITECTURE_INTERVIEW_GUIDE.md) — architecture,
  agent communication, framework comparisons, and interview answers.
- [`FINAL_DEMO.md`](FINAL_DEMO.md) — preflight checks, demo sequence, expected figures, and recovery.
- [`SYNTHETIC_DEMO_SCENARIO.md`](SYNTHETIC_DEMO_SCENARIO.md) — demo holdings, cost basis, planted
  risks, health-score math, suggestions, and intentional data gaps.
- [`docs/EVALUATION.md`](docs/EVALUATION.md) — evaluation questions, final results, reproducibility,
  and limitations.
- [`docs/PRIVACY_AND_DATA_SAFETY.md`](docs/PRIVACY_AND_DATA_SAFETY.md) — repository and runtime data
  boundaries for safe use.
- [`docs/final/FINAL_CAPSTONE_REPORT.md`](docs/final/FINAL_CAPSTONE_REPORT.md) — cohesive final report
  draft following the official capstone outline.
- [`docs/final/FINAL_PRESENTATION.md`](docs/final/FINAL_PRESENTATION.md) — ten-slide narrative,
  visible copy, demo sequence, timing, and speaker notes.
- [`docs/final/SUBMISSION_CHECKLIST.md`](docs/final/SUBMISSION_CHECKLIST.md) — final artifact,
  repository-release, recording, and Canvas checks.
- [`StudyGuide/`](StudyGuide/README.md) — learn-as-you-build curriculum.

Base currency: **USD**. Package manager: **uv**.

Licensed under the [MIT License](LICENSE).
