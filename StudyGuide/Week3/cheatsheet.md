# Week 3 Cheat-Sheet — Reasoning (ReAct), Orchestrator & LangGraph
*(Aligned to CMU Module 3: Reasoning & Agent Architectures)*

## Reasoning patterns (increasing structure)
- **CoT** — think step-by-step in one generation. Helps (conditions on own steps) but **can't act**, errors propagate.
- **ReAct** — **Thought → Action (tool) → Observation → repeat.** Grounded (real results), recovers from missteps. **Setu's core loop.**
- **ToT** — branch into N candidates, score, keep best. Expensive → Setu uses it **only for reconciliation** (Wk4).

> CoT = "think harder" · ReAct = "think + use tools" · ToT = "pick the verified answer."

## ReAct cycle
```
THOUGHT → ACTION (tool call) → OBSERVATION (real result) → THOUGHT → … → STOP
```
- **Grounding** — model observes real tool output, never invents the number (operationalizes "no LLM computes").
- **Recovery** — a failure/low-confidence result is *just another observation* → next Thought re-plans (different tool / re-parse / ask user). **Graded success metric.**

## Orchestrator = ReAct planner over sub-agents
Its "actions" include **dispatching sub-agents** (`IngestionAgent`, `ReconciliationAgent`, `InsightsAgent`).
Reads their results, re-plans on failure, runs independent statements **in parallel**.
→ This is where **reasoning (concept #2)** meets **multi-agent (concept #5)**.

## LangGraph = the runtime (state machine)
| Primitive | What | Setu file |
|---|---|---|
| **State** | `TypedDict` every node reads/writes = **working memory** | `state.py` |
| **Node** | `(state) → partial update`; wraps agent/tool | `nodes.py` |
| **Edge** | next step; **normal** or **conditional** | `build.py` |

**`build.py`** (assemble once, invoke per command): register nodes → wire edges → **compile with a `SqliteSaver` checkpointer**.
The **conditional edge after `reconcile`** (`ok→persist / mismatch→ask_user / retry→replan→reconcile`) = the **self-correcting branch** (ToT decision as control flow). `retry` goes through a `replan` node that bumps a bounded counter so a persistent mismatch escalates to the human instead of looping forever.

## SQLite checkpointer — snapshots State after every node, keyed by `thread_id`
1. **Durability/resumability** — crash mid-ingest → same `thread_id` resumes from last checkpoint; done work not redone.
2. **Human-in-the-loop** — the `ask_user` node calls **`interrupt({question,…})`** → **pauses + persists**; `invoke` returns frozen with the question under `__interrupt__`; later `invoke(Command(resume="accept"))` continues, State intact — even from a **new process** on the same checkpoint file. **Without it, a paused run loses working memory.** (Dynamic `interrupt()` vs static `interrupt_before` — use one, not both.)
3. **Conversation continuity** — reuse `thread_id` across `setu ask` → follow-ups keep context = **short-term memory**, free.
4. **Audit/time-travel** — per-step State history → provenance guardrail (Wk6).

## Two SQLite DBs — DON'T conflate
| DB | Holds | Memory | When |
|---|---|---|---|
| **Checkpointer DB** | run/conversation State per `thread_id` | working + short-term | Wk3 |
| **Ledger DB** | accounts/holdings/balances/FX (financial truth) | long-term | Wk1 |
Same engine, different tables/lifetimes. Checkpointer = *train of thought*; ledger = *source of truth for money*.

## Memory-type mapping (ties to DESIGN_personas_memory.md)
**working = State · short-term = checkpointer · long-term = ledger + vector store.**

## Week 3 build ↔ theory
`IngestionAgent` (first sub-agent) + Orchestrator ReAct loop w/ **visible traces** (→ Agent Feed) +
LangGraph skeleton (`state/nodes/build`) compiled with `SqliteSaver`. Runs end-to-end for one
statement, already **durable + resumable** before ToT (Wk4) / RAG (Wk5).

> **Punchline:** ReAct = think/act/observe/recover; LangGraph + checkpointer = durable, resumable,
> interruptible runtime. Reasoning without a runtime is a prompt; a runtime without reasoning is a script.

## Key terms
Chain-of-Thought · ReAct · Tree-of-Thought · Thought/Action/Observation · grounding · re-planning ·
orchestrator · sub-agent · multi-agent coordination · StateGraph · node · conditional edge · State (TypedDict) ·
checkpointer · `thread_id` · `interrupt()` / `interrupt_before` · `__interrupt__` · `Command(resume=…)` · durability/resumability · time-travel
