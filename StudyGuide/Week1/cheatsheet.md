# Week 1 Cheat-Sheet — LLM Internals & Why Agents
*(Aligned to CMU Module 1: Foundations of Agentic AI & LLM Capabilities)*

## LLM in one line
A **next-token predictor**: learns a **probability distribution over token sequences**; generates via
**autoregressive next-token prediction**. Not a database, calculator, or logic engine. Fluency ≠ truth.

## The pipeline
`text → tokens → embeddings → transformer layers (self-attention) → probability over vocab → sample → append → repeat`

- **Token** — sub-word unit (~4 chars); model sees IDs, not letters → *why it miscounts/mis-maths*.
- **Embedding** — token → vector; similar meanings sit close *(reused for RAG, Wk5)*.
- **Self-attention** — each token → **query/key/value (Q/K/V)**; scores pairwise relevance; replaces
  recurrence → **parallel** processing; order & phrasing matter.
- **Positional encodings** — inject order info (attention alone has none).
- **Decoder-only + causal masking** — generate one token at a time; each position sees only earlier ones.
- **Temperature** — high = creative/random, low = consistent. **Setu uses low temp.**
- **Context window** — the only thing it "knows" now = weights + current window. **No memory between calls.**
- **Knowledge cutoff** — weights frozen at training time → no live data.

## Training & scaling
- **Objective:** minimize **cross-entropy loss** (surprise at the true next token).
- **Pre-training** → language + world knowledge (to cutoff); **Post-training (instruction tuning + RLHF)** → follows instructions.
- **Scaling laws:** loss falls as a **power law** of **data × parameters × compute** (predictable).
  → **emergent capabilities** at scale. BUT attention cost is **quadratic in context length**, and
  **scaling never fixes math / live data / hallucination** → that's the case for agents.

## Failure modes → Setu's response
| Fails at | Setu does |
|---|---|
| Exact math | `calc.py`/`risk.py` compute all numbers deterministically |
| Hallucination | numbers only from docs; reconcile; missing → ask, never invent |
| No live data | FX/NAV via **tools** |
| No memory | external store + RAG (Wk5) |
| Prompt sensitivity | low temp + structured output + validation |
| Overconfidence/sycophancy | confidence thresholds → human-in-the-loop |
| Prompt injection | treat doc text as untrusted; guardrails (Wk6) |

## Mental model
> A brilliant, fast intern who is **confidently wrong** at a predictable rate, **can't use a
> calculator**, **forgets everything** between chats, and **read the news only up to last year.**
> Great for reading/classifying/drafting — never for wiring money without a deterministic check.

## Prompt response vs. agent (course's central distinction)
- **Prompt response** = single forward pass; **no memory, no verification, no iteration**.
- **Agent** = LLM embedded in a system that **operates over time**.

**5 core components (memorize):** **Goals · Perception · Memory · Reasoning · Action.**
**Environment** = what it can observe + actions available (tools, data sources, users).
**Feedback** = signals about outcomes that guide the next step.

**The loop:** `OBSERVE → REASON → ACT → FEEDBACK → (repeat)` — enables error correction, iteration,
goal-directed behavior. Needs live data → act/tools · exact numbers → compute + reconcile feedback ·
recover → observe-reason-retry (Wk3) · remember → memory (Wk5) · safe → guardrails (Wk6).

> **Punchline:** agents beat the limits of scaling by adding **structure + tools + feedback**, not a bigger model.

## LLM's role in Setu
LLM decides **which tool to call** and **interprets results** — it never computes the numbers.

## Week 1 build ↔ theory
Build the **deterministic substrate first** (SQLite schema + synthetic data w/ known totals), *then*
layer the probabilistic LLM on top with verification. Safety-first = trustworthy core before intelligence.

## Key terms
token · embedding · self-attention (Q/K/V) · positional encoding · causal masking · decoder-only ·
autoregression · cross-entropy loss · scaling laws · emergent capabilities · temperature/top-p ·
context window · knowledge cutoff · pre-training · RLHF · fragility · hallucination · grounding ·
agent · goals/perception/memory/reasoning/action · observe-reason-act-feedback
