# Week 1 — How LLMs Work, Where They Fall Short, and Why We Need Agents

**Build this week:** repo scaffold, SQLite schema, synthetic portfolio generator.
**Study goal:** understand the machine at the center of Setu well enough to know *what to trust it
with and what not to* — the single most important design instinct for the whole project.

> **Aligned to CMU Module 1** ("Foundations of Agentic AI & LLM Capabilities"). Course learning
> outcomes: (1) how LLMs are constructed + role of **scaling laws**; (2) LLM limitations — fragility,
> scaling constraints, cross-model inconsistency; (3) the **core components of an agent — goals,
> perception, memory, reasoning, action**; (4) prompt outputs vs. structured **agent workflows**;
> (5) defining an initial agent concept (goal, environment, reasoning steps, structure). This
> explainer covers all five and grounds them in Setu.

---

## 1. What an LLM actually is

A large language model is a **next-token predictor**. Given a sequence of tokens, it outputs a
probability distribution over the next token, samples one, appends it, and repeats. Everything an LLM
appears to "do" — reason, summarize, classify, plan — is an emergent consequence of doing this
extremely well over enormous training data. It is not a database, a calculator, or a reasoning engine
with a symbol table; it is a statistical model of "what text plausibly comes next."

### The pipeline, end to end
1. **Tokenization.** Text is split into *tokens* (sub-word chunks, ~4 chars on average). `"Fidelity"`
   might be one token; `"₹6,98,000"` several. Models see token IDs, not characters — which is exactly
   why they miscount digits and mangle arithmetic (see §2).
2. **Embeddings.** Each token ID maps to a high-dimensional vector. Semantically similar tokens sit
   near each other in this space. *(This is the same embedding idea we exploit for RAG in Week 5.)*
3. **Transformer layers + attention.** The core mechanism is **self-attention**: for each position,
   the model computes how much every other token should influence it. Concretely, each token is
   projected into **query, key, and value (Q/K/V)** vectors; attention scores every token pair by
   query·key relevance and mixes the values accordingly. Transformers **replace recurrence** (older
   RNNs processed tokens sequentially) with attention, which lets the whole sequence be processed **in
   parallel**. Because attention itself has no notion of order, **positional encodings** inject
   sequence-position information. Setu's models are **decoder-only** — they generate one token at a
   time using **causal masking** (each position may attend only to earlier positions, never peek
   ahead). Stacked attention layers build contextual meaning — "bank" near "river" vs. "deposit" —
   which is why the model is sensitive to *how* you phrase and order information.
4. **Output distribution + sampling.** The final layer produces a probability over the whole
   vocabulary. **Sampling** controls how a token is chosen:
   - *Temperature* — higher = more random/creative, lower = more deterministic. For Setu's extraction
     and classification we want **low temperature** (consistency, reproducibility).
   - *Top-p / top-k* — restrict sampling to the most probable tokens.
5. **Autoregression.** The chosen token is fed back in; repeat until a stop condition. This left-to-
   right generation is why the model can't "go back and fix" an earlier token — it commits as it goes.

### Context window
The model can only attend to a bounded number of tokens (the **context window** — e.g. tens of
thousands to ~1M). Everything the model "knows" in a given call is: its trained weights + whatever is
in the context window right now. It has **no memory between calls** unless we put it there. *(This
single fact is why Setu needs an external memory store — Week 5.)*

### How training works (the objective)
During training the model **minimizes cross-entropy loss** — a measure of how surprised it is by the
*actual* next token given the prior context. Lower loss = it assigned higher probability to the
correct token. Training nudges the weights to make correct continuations more likely across billions
of examples. Two stages:
- **Pre-training** — minimize next-token loss over a huge corpus → general language + world knowledge
  (up to a **knowledge cutoff** date).
- **Post-training (instruction tuning + RLHF/RLAIF)** — align the model to follow instructions and
  human preferences. This is what turns a raw predictor into a usable assistant.

### Scaling laws (a course headline — why models got good)
**Scaling laws** show that model **loss decreases predictably as a power-law function** of three
inputs: **data size, parameter count, and compute**. Scale them up together and loss falls in a
smooth, forecastable way — this predictability is what justified the industry's massive investment.
Two consequences matter for us:
- **Emergent capabilities** — beyond certain scales, qualitatively new abilities appear (better
  reasoning, in-context learning, generalization) that weren't present in smaller models.
- **Scaling is not free and not sufficient.** Attention cost grows **quadratically with context
  length**, so longer contexts mean more memory/compute and more instability. And crucially — *no
  amount of scaling makes the model do exact math, know today's FX rate, or stop hallucinating.*
  **This is the core argument of the course and of Setu:** past a point, you get reliability by
  **adding structure, tools, and feedback (an agent)** — not by reaching for a bigger model.

---

## 2. Where LLMs fall short (the failure modes Setu must design around)

Each limitation below maps directly to a design decision we've already made.

| Limitation | Why it happens | Setu's design response |
|---|---|---|
| **Bad at exact arithmetic** | Numbers are tokenized oddly; the model predicts *plausible-looking* digits, not computed results | **No LLM ever does math.** `calc.py` / `risk.py` compute every balance, %, and FX conversion deterministically |
| **Hallucination** | The model always produces *fluent* output, even when it has no grounding — it optimizes plausibility, not truth | Numbers come only from documents; **reconciliation** verifies totals; missing data → ask user, never invent (deep-dive Week 4) |
| **Knowledge cutoff / no live data** | Weights are frozen at training time | FX rates, NAVs, prices come from **tools**, not the model (Week 2) |
| **No persistent memory** | Stateless between calls; only the context window | External **memory store** + RAG (Week 5) |
| **Context limits & "lost in the middle"** | Finite window; recall degrades for info buried mid-context | Retrieve only *relevant* context; keep prompts focused (Week 5) |
| **Fragility / prompt sensitivity** | Sampling + phrasing effects — *small prompt changes → very different outputs* (course term: **fragility**) | Low temperature, structured output schemas, validation (Week 2) |
| **Cross-model inconsistency** | Behavior varies across providers due to differences in architecture, training data, and context limits | Config-driven model router; pin models; validate outputs regardless of model |
| **Optimizes likelihood, not truth** | The training objective rewards *plausible* text, not correctness, grounding, or task success | Ground every claim in documents/tools; deterministic verification |
| **Sycophancy / overconfidence** | RLHF rewards agreeable, confident answers | Confidence thresholds → human-in-the-loop; guardrails (Week 6) |
| **Prompt injection** | The model can't inherently tell instructions from data | Treat statement text as untrusted; redaction + guardrails (Week 6) |

**The mental model to internalize:** an LLM is a brilliant, fast, well-read intern who is
*confidently wrong* at a predictable rate, cannot use a calculator, forgets everything between
conversations, and read the news only up to last year. You would never let that intern wire money —
but you'd absolutely use them to read a messy statement, classify it, and draft an explanation, *as
long as a deterministic system checks their numbers.* That sentence is Setu's entire architecture.

---

## 3. Prompt response vs. agent workflow (the course's central distinction)

The course draws a sharp line:

- **A prompt response is a single forward pass** through the model — text in, text out, with **no
  memory, no verification, no iteration.** It generates once and stops.
- **An agent embeds the LLM within a system that operates over time.** The model is just one
  component; the surrounding structure is what produces reliable, goal-directed behavior.

### The five core components of an agent (course vocabulary)
Memorize these — they're a stated learning outcome and the language your report should use:

| Component | What it is | In Setu |
|---|---|---|
| **Goals** | What the agent is trying to achieve | "Consolidate the portfolio; report net worth, allocation, and risk-vs-target" |
| **Perception** | How it observes its environment | Parsing statements (PDF/CSV), reading tool outputs, receiving user answers |
| **Memory** | What it retains across steps/runs | SQLite ledger + vector store (past runs, corrections, policy-rules KB) — Week 5 |
| **Reasoning** | How it decides what to do next | The ReAct orchestrator (Week 3), Tree-of-Thought reconciliation (Week 4) |
| **Action** | How it affects the environment | Tool calls (`fx`, `calc`, `reconcile`), writing to the ledger, asking the user |

The course also names the surroundings explicitly: the **environment** defines what the agent can
observe and the actions available (tools, data sources, users); **actions** affect that environment
(tool calls, code execution, data retrieval); **feedback** provides signals about action outcomes
that guide the next decision. *(This is exactly the environment/actions/feedback structure Checkpoint
1 asked us to specify for Setu.)*

### The agent loop: observe → reason → act → feedback
Instead of a single generation step, an agent runs a **loop**:

```
        ┌───────────────────────────────────────────────┐
        ▼                                                │
   OBSERVE ──▶ REASON ──▶ ACT ──▶ (environment changes) ─┘  ← FEEDBACK guides the next loop
  (perceive)  (decide)  (tool/    outcome observed,
                         action)  fed back in
```

This structure is what enables **error correction, iteration, and goal-directed behavior** beyond
plain text generation. Setu's job breaks the one-shot model on every axis — and each break is
answered by a loop component:

- Needs **live external data** (FX, NAVs) → **act** via tools.
- Needs **exact, verifiable numbers** → deterministic compute + **feedback** via reconciliation.
- Is **multi-step and stateful** → the loop + **memory**.
- Must **recover from mistakes** (misparse, ambiguous policy) → **observe** the failure, **reason**,
  retry (ReAct, Week 3).
- Must **not do unsafe things** → guardrails constrain **action** (Week 6).

> **The course's punchline (and Setu's thesis):** agent design addresses the limits of scaling by
> **adding structure, tools, and feedback — not by relying on a bigger model.** The LLM is the
> reasoning core; the agent is the system around it that makes the reasoning *reliable*.

### Where the LLM sits in Setu (preview of the whole design)
```
                 ┌─────────────────────────────────────────────┐
   documents ───▶│  LLM (reason / classify / explain / decide)  │◀── retrieved memory (RAG)
                 └───────┬───────────────────────▲──────────────┘
                         │ decides to call        │ observes results
                         ▼                        │
                 ┌───────────────┐   deterministic, exact
                 │ TOOLS         │   fx / calc / reconcile / risk
                 └───────────────┘
   The LLM never computes the numbers — it decides *which* tool to call and *interprets* the result.
```

---

## 4. Connection to what we build in Week 1

This week's code is deliberately *pre-LLM* — and that's the point. Before adding any intelligence, we
build the **deterministic substrate** the LLM will later operate over:

- **SQLite schema** (`Account`, `Holding`, `PolicyValue`, `Balance`, `RiskProfile`) — the structured,
  factual world the agent reasons about. Facts live here, *not* in the model's head.
- **Synthetic portfolio generator** — gives us ground-truth data with *known* correct totals, so when
  we later add the LLM we can measure exactly where it helps and where it errs (this is the seed of
  our golden-file tests and hallucination detection).

Building the trustworthy, deterministic core *first* — then layering the probabilistic LLM on top with
verification — is the safety-first pattern that runs through the entire project.

---

## 5. Further reading (optional)
- "Attention Is All You Need" (Vaswani et al., 2017) — the transformer.
- The Illustrated Transformer (Jay Alammar) — visual intuition for attention.
- Anthropic / OpenAI docs on sampling parameters and structured outputs.
- Course Module 1 materials on LLM limitations and the case for agents.

See `cheatsheet.md` for the one-page recall version.
