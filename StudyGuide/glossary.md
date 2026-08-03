# Setu Study Guide — Running Glossary

Grows week over week. Terms are added as each week's material introduces them.

## Week 1 — LLM internals & agents
- **Token** — a sub-word unit of text (~4 chars) the model actually processes as an ID; the reason
  LLMs miscount digits and struggle with exact arithmetic.
- **Embedding** — a token (or text) mapped to a high-dimensional vector where semantic similarity =
  geometric closeness. Basis for RAG retrieval.
- **Self-attention** — the transformer mechanism where each token weighs the relevance of every other
  token; produces context-sensitive meaning.
- **Autoregression** — generating one token at a time, feeding each back in; the model commits
  left-to-right and can't revise earlier tokens.
- **Temperature / top-p / top-k** — sampling controls; low temperature = more deterministic
  (what Setu uses for extraction/classification).
- **Context window** — the bounded span of tokens a model can attend to in one call; combined with
  its weights, it's *all* the model knows at that moment.
- **Knowledge cutoff** — the date after which the model has no trained knowledge; why live data needs
  tools.
- **Pre-training** — next-token training over a large corpus → general knowledge.
- **RLHF** — Reinforcement Learning from Human Feedback; post-training alignment to human preferences.
- **Hallucination** — fluent, confident output that is ungrounded/false; the model optimizes
  plausibility, not truth. (Deep-dive Week 4.)
- **Grounding** — tying model output to verifiable sources/data rather than its parametric memory.
- **Query / Key / Value (Q/K/V)** — the three learned projections of each token that self-attention
  uses; relevance = query·key, output = relevance-weighted sum of values.
- **Positional encoding** — information added to token representations to convey sequence order, which
  self-attention does not capture on its own.
- **Causal masking** — restricts each position to attend only to earlier positions; enables
  left-to-right (decoder-only) generation.
- **Decoder-only architecture** — the generate-one-token-at-a-time transformer design used by modern
  LLMs (via causal masking).
- **Cross-entropy loss** — the training objective; measures how improbable the true next token was
  under the model. Training minimizes it.
- **Scaling laws** — empirical power-law relationship: loss decreases predictably as data, parameters,
  and compute increase.
- **Emergent capabilities** — abilities (reasoning, in-context learning, generalization) that appear
  only past certain model scales.
- **Fragility** — an LLM limitation: small prompt changes can cause large output changes.
- **Agent** — an LLM embedded in a system that operates over time; core components: **goals,
  perception, memory, reasoning, action**. Makes LLM reasoning reliable via structure, tools, feedback.
- **Environment** — what the agent can observe and the actions available to it (tools, data sources,
  users).
- **Feedback** — signals about action outcomes that guide the agent's subsequent decisions.
- **Observe → reason → act → feedback loop** — the agent workflow that replaces a single generation
  step and enables error correction and goal-directed behavior.
