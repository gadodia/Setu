# Setu Study Guide

A learn-as-you-build curriculum. Each week pairs **what we implement** in Setu with **the theory
behind it**, so the concepts from the CMU Agentic AI course are grounded in a real system. Every
topic has a **deep explainer** (concepts → why it matters → how Setu uses it → tradeoffs → pitfalls)
and a **one-page cheat-sheet** for quick recall/revision.

> How to use: read the week's explainer *before* implementing, skim the cheat-sheet *after* to
> consolidate. The "How Setu uses it" section connects each abstract idea to concrete code we write.

## Week → build → theory map

| Week | What we build (roadmap) | Study topics | Graded concept |
|---|---|---|---|
| **1** | Repo scaffold, SQLite schema, synthetic portfolio generator | **LLM internals** — how LLMs work (tokens, embeddings, attention, next-token prediction, context windows, sampling); where they fall short; **why agents are needed** | Foundations |
| **2** | Deterministic tools (`pdf_extract`, `fx`, `calc`) + tool calling | **Tool / function calling** — how tool use works internally, JSON-schema tools, structured output, when to use deterministic code vs the LLM | #1 Tool Calling |
| **3** | Orchestrator ReAct loop + `IngestionAgent` | **Reasoning architectures** — Chain-of-Thought, ReAct (reason+act+observe), agent design patterns, control flow, recovering from missteps | #2 Reasoning / CoT |
| **4** | `ReconciliationAgent` with Tree-of-Thought + human-in-the-loop | **Further reasoning + hallucinations** — Tree-of-Thought, self-consistency, reflection; why LLMs hallucinate, taxonomy, and mitigation (grounding, verification, deterministic checks) | #4 Further Reasoning |
| **5** | RAG memory (vector store) + `risk.py` analysis | **Knowledge & memory** — embeddings, RAG, chunking/retrieval; short- vs long-term memory; **relational vs vector vs graph** stores and when each fits | #3 Memory |
| **6** | Guardrail layer + written safety statement | **Safety & alignment** — guardrails, prompt injection, PII/data-leakage, action gating, human-in-the-loop, evaluating safety, unintended actions | #6 Safety |
| **7** | `InsightsAgent` Q&A + polish + report | **Multi-agent + system design** — multi-agent coordination, orchestration/parallelism, evaluation of agentic systems, cost/latency/quality tradeoffs, putting it together | #5 Multi-agent |

## Cross-cutting threads (revisited most weeks)
- **Determinism vs. probabilism** — what the LLM decides vs. what code computes (a spine of Setu's design).
- **Provenance & trust** — every number traceable to a source; never invented.
- **Human-in-the-loop** — where and why the agent pauses for the user.

## Companion research: the industry landscape
- **[IndustryLandscape/](IndustryLandscape/README.md)** — a wide-angle survey of *how agentic systems
  are solving real problems across industries, how widely they're adopted, what blocks them, and where
  India lags or leaps.* Eight parallel research passes (finance, healthcare, software/IT, support/BPO,
  manufacturing, logistics, legal/retail, India-emerging) plus a synthesis showing the whole industry
  converges on the *same* architecture Setu uses. Read the synthesis README first; it maps every finding
  back to Setu's Checkpoint-2 design.

## Folder layout
```
StudyGuide/
├── README.md            ← this index
├── Week1/
│   ├── explainer.md     ← deep explainer
│   └── cheatsheet.md    ← one-page recall sheet
├── Week2/ ...           ← generated as we implement each week
└── glossary.md          ← running glossary of terms (grows weekly)
```

Status: **Weeks 1 and 3 written** (Week 1 as the foundational sample; Week 3 covers ReAct + LangGraph +
the SQLite checkpointer). Remaining weeks generated as we implement them.
