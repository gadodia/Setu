# Setu: Agent Design Refinement

**CMU Agentic AI Capstone — Checkpoint 2.1: Reasoning, Memory, and Tools**

## Refined agent concept and task

Setu (Hindi for "bridge") is a cross-border **wealth and portfolio agent**. It consolidates one
individual's assets scattered across US and Indian institutions — brokerage and retirement accounts,
Indian mutual funds, bank balances, and insurance policies (LIC, ULIP, endowments) — into a single
currency-normalized view, then answers: *what am I worth, how is that allocated across asset classes,
geographies, and currencies, and does it match my declared risk appetite?* This module adds no new
features; it makes explicit **which reasoning, memory, and tool capabilities each known limitation
forces on the design**, justified against the failure each prevents.

## Reasoning loop

Setu's core is a **ReAct loop** (Thought → Action → Observation → repeat) driven by an orchestrator.
Given a goal like "how far is my allocation from target?", it reasons about the next step, calls one
tool or delegates to a sub-agent, observes the structured result, and lets that shape the next
thought. Answering "what is my real INR exposure?" unfolds as: query the ledger → get holdings by
currency → `fx` lookup → `calc` → the exposure figure. Each observation is a branch point: a failed
parse or low-confidence extraction is recorded and triggers **re-planning** — a different tool, a
re-parse, or a human question — rather than a crash. Where the solution space genuinely branches,
Setu escalates to **Tree-of-Thought**: when parsed totals don't match a statement's stated balance,
reconciliation generates several parse hypotheses, scores each against the stated total, and keeps
the one that balances (or interrupts the user). ReAct for the common path, ToT where hypotheses
compete — this is what turns a brittle pipeline into a self-correcting one.

## Memory

Setu needs **both short-term and long-term memory** for different jobs.

**Short-term (working) memory** holds one run's state: the current goal, intermediate tool outputs,
partial extractions, and the thought/observation trace. A LangGraph checkpointer persists this so a
multi-step ingestion is durable and resumable — essential because a run may pause for a human
confirmation and must resume with full context.

**Long-term memory** spans runs and is where reliability compounds, across three stores: (a) a
**relational ledger** (SQLite) — the source of truth for accounts, holdings, balances, FX rates, and
obligations, since the domain is numeric and relational and exact aggregation/dedup is SQL's home
turf; (b) a **vector store** for semantic recall — how a similar statement was parsed before, or
matching a holding to a past correction; and (c) a small **knowledge base** of policy-valuation
rules. It matters precisely when the agent must not repeat mistakes: a correction to a mis-classified
ULIP is stored once and *retrieved* next time a similar policy appears, so the agent improves instead
of re-erring.

## External tools

Tool use is non-negotiable because of a hard limitation: **LLMs cannot do reliable arithmetic and
don't know current external data.** The rule baked into Setu is that *no LLM ever computes a financial
figure.* Net worth, allocation percentages, and currency exposures come from deterministic Python
tools (`calc`, `risk`); current FX rates come from an `fx` tool, not the model's memory. Computing net
worth across a USD brokerage account and an INR mutual fund needs both *grounding* (a real, current FX
rate) and *exact computation* (summing converted holdings) — both outside a language model's
competence. The LLM is confined to what it's good at: reading a statement, classifying a holding,
deciding which tool to call, and explaining the result. A companion `reconcile` tool checks summed
values against each statement's stated total before any number is trusted.

## Improvement over a prompt-only approach

A prompt-only approach fails on a demonstrable failure mode: **confident numeric hallucination.**
Asked to total a multi-currency portfolio, a bare LLM produces a plausible but wrong figure — it
invents an FX rate from stale training data and makes arithmetic slips, with no way for the user to
catch either. Setu resolves this directly: the **tool** layer removes computation from the model, so
the number is exact and the FX rate is real; the **reasoning loop** forces reconciliation before any
figure is surfaced, so a mismatch is caught rather than shipped; **memory** ensures a correction made
once applies forever, and the ledger keeps every number traceable to its source. Each capability
answers a specific limitation — probabilistic math (tools), single-shot brittleness (ReAct/ToT
re-planning), and statelessness (memory) — which is why an agent architecture, not a better prompt,
is the right answer for this task.
