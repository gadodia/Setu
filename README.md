# Setu (सेतु)

> Sanskrit/Hindi for **"bridge."** Setu bridges an individual's finances across the **US and India**
> into one clear view.

Setu is a cross-border **wealth & portfolio agent** (CMU Agentic AI capstone). It consolidates one
person's assets scattered across US and Indian institutions — brokerage & retirement accounts, Indian
mutual funds, bank balances, and insurance policies (LIC, ULIP, endowments) — across currencies and
incompatible statement formats into a single **net-worth, asset-allocation, and risk-vs-target** view.

**Design principle:** the LLM decides, classifies, and explains; **deterministic Python computes every
financial figure.** No LLM ever computes a number — see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Status

Week 1 — **deterministic substrate**: config, SQLite ledger, synthetic portfolio generator, and the
`calc`/`fx` tools, all LLM-free. LangGraph agents, parsers, memory, and the dashboard arrive in later
weeks (see the 7-week roadmap in `ARCHITECTURE.md §6`).

## Quickstart

```bash
uv sync                     # create the venv + install deps
uv run setu init-db         # create the SQLite schema
uv run setu seed            # generate a synthetic US+India portfolio
uv run setu report          # print net worth + allocation (USD base)
uv run pytest               # golden-file tests: computed totals == known truth
```

## Docs

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — full design & path forward.
- [`DESIGN_personas_memory.md`](DESIGN_personas_memory.md) — personas + memory architecture.
- [`DESIGN_prior_art.md`](DESIGN_prior_art.md) — competitive landscape & reuse decisions.
- [`StudyGuide/`](StudyGuide/README.md) — learn-as-you-build curriculum.

Base currency: **USD**. Package manager: **uv**.
