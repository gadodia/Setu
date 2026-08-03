# Week 2 Cheat-Sheet — Tool / Function Calling (the determinism spine)
*(Aligned to CMU Module 2: Tool / Function Calling)*

## Why tool calling exists
A bare LLM has no calculator/clock/filesystem and frozen knowledge → it *pattern-matches* numbers (confidently wrong, untraceable). Tool calling lets the model **decide what to do** while **deterministic code does it.**
> **LLM decides / classifies / explains. Python computes. No LLM ever computes a financial figure.**

## What a "tool" IS (over the wire)
A **JSON-schema description of a function** + the real function on your side.
1. Send user msg **+ tool schemas** to model.
2. Model emits a **`tool_use`** block `{name, input}` — names the fn, fills args (schema-constrained). It does **not** run anything.
3. **Your code** runs the real function → result.
4. Feed result back as **`tool_result`**.
5. Model reads observation → another tool, or final answer.
> **Model emits *intent*; your runtime supplies *fact*.**

## Two modes in Setu (know why there are two)
| | (a) Agentic loop — Claude | (b) Structured output — Ollama |
|---|---|---|
| Chooses tool | model, autonomously | you (1 fixed schema) |
| Rounds | many, until `end_turn` | exactly one |
| Command | `setu ask` (open reasoning) | `setu ingest` (extraction) |
| Runs where | cloud (no raw PII) | **local (PII stays home)** |
| Guarantee | flexible | output always matches schema |

- **(a) `run_tool_loop`** (`llm/claude.py`): loop while `stop_reason=="tool_use"`, stop on `end_turn`. Open-ended.
- **(b) `extract_structured`** (`llm/local.py` + `extraction.py`): Ollama `format=<JSON schema>` = **constrained decoding**, always parses → validated pydantic.

## Hybrid model strategy (privacy = routing)
Raw statement text (account #s, names, balances) → **local model only**, never leaves machine. Cloud Claude reasons where there's no raw PII. `llm/router.py` picks provider per stage from `config.yaml`.

## The design rule — deterministic code vs LLM
> **One correct answer computable from data → Python. Needs judgment / classification / language → LLM.**

| Job | Who | Why |
|---|---|---|
| sum, FX convert, allocation % | `calc.py`/`fx.py` (`Decimal`) | one right answer, exact, testable |
| PDF → text+tables | `pdf_extract.py` | mechanical |
| "EQUITY or DEBT? US or India?" | LLM | classify messy text |
| "which tool answers this?" | LLM (loop) | plan in context |
| "explain my USD overweight" | LLM (insights) | NL over computed facts |

**Anti-patterns:** ❌ LLM-as-calculator (non-deterministic, unauditable) · ❌ regex-as-classifier (brittle per-format). `money` = **`Decimal` everywhere, never `float`.**

## Week 2 build ↔ theory
`pdf_extract` (deterministic parse) + `fx`/`calc` (compute core) + `tools/registry.py` (`TOOL_SCHEMAS` + `build_executor` dispatch, Decimals→str) + `llm/local`+`extraction` (constrained output, private) + `llm/claude`+`router` (agentic loop). Exposed as `setu ingest` / `setu ask --trace` (T/A/O trace previews Wk3 ReAct).
Tests assert **exact** figures (`Decimal("262413.3000000")`) — determinism is verifiable.

> **Punchline:** a tool = a JSON-schema fn the model can *call but not execute*. Autonomous loop for open reasoning (Claude); constrained structured output for private extraction (Ollama). LLM decides, Python computes, no number is the model's invention.

## Key terms
tool / function calling · JSON-schema tool · `tool_use` / `tool_result` · agentic loop · `stop_reason` · constrained decoding · structured output (`format=`) · pydantic validation · hybrid model strategy · model router · PII locality · determinism vs probabilism · `Decimal` money · classification vs computation
