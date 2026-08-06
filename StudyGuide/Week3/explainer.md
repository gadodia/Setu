# Week 3 — Reasoning Architectures, the Orchestrator, and LangGraph

**Build this week:** the Orchestrator **ReAct loop** + `IngestionAgent`; the **LangGraph skeleton**
(`state.py`, `nodes.py`, `build.py`) with a **SQLite checkpointer**; visible thought/action/observation
traces.
**Study goal:** understand *how an LLM is turned into a controllable, resumable agent* — the reasoning
pattern (ReAct) and the runtime that executes it (LangGraph + checkpointer). This is where Week 1's
"agent loop" stops being a diagram and becomes running code.

> **Aligned to CMU Module 3** ("Reasoning & Agent Architectures"). Outcomes: (1) **Chain-of-Thought**
> and why intermediate reasoning helps; (2) **ReAct** (reason + act + observe) and tool-augmented
> reasoning; (3) agent **control flow** — planning, delegation, recovering from missteps; (4) the
> engineering substrate that makes multi-step agents **stateful and durable**. Grounded in Setu.

---

## 1. Why reasoning architectures exist

A single forward pass (Week 1) commits to an answer token-by-token with no chance to plan, check, or
recover. **Reasoning architectures** are prompting/control patterns that give the model room to think
and act in steps. Three that matter, in increasing structure:

- **Chain-of-Thought (CoT).** Prompt the model to produce intermediate reasoning ("let's think step by
  step") before the answer. Helps because each generated reasoning token becomes context for the next,
  so the model conditions its answer on its own worked steps instead of blurting a guess. But CoT is
  still **one uninterrupted generation** — it can reason *about* an FX rate but cannot go *fetch* one,
  and if a step is wrong the error just propagates.
- **ReAct (Reason + Act).** Interleaves reasoning with **actions against the world**: Thought → Action
  (call a tool) → Observation (the tool's real result) → Thought → … Each observation is *real
  external data*, not the model's guess, so the loop is **grounded** and can **course-correct**. This
  is Setu's core loop.
- **Tree-of-Thought (ToT).** When the solution space branches, explore *several* candidate lines,
  score them, keep the best. Setu uses this specifically for reconciliation (Week 4) — not for every
  step, because it's more expensive.

The rule of thumb: **CoT for "think harder," ReAct for "think *and* use tools," ToT for "several
plausible answers — pick the verified one."**

---

## 2. ReAct in depth (Setu's core loop)

ReAct's unit is the **Thought → Action → Observation** cycle, repeated until the goal is met:

```
   THOUGHT      "To answer INR exposure I need holdings + a current FX rate."
      │
   ACTION       call tool: fx(base="INR")            ← the model emits a structured tool call
      │
   OBSERVATION  {"USDINR": 83.1}                      ← real result, fed back into context
      │
   THOUGHT      "Now sum USD holdings × 83.1 + INR holdings."
      │
   ACTION       call tool: calc(...)
      │
   OBSERVATION  {"inr_exposure": 3620000}
      │
     ...        (repeat until the agent has the answer, then STOP)
```

Two properties are the whole point:

- **Grounding.** The model never *invents* the FX rate — it observes a tool's real output. This is how
  ReAct operationalizes Week 1's "no LLM computes a number": the LLM decides *which* tool and
  *interprets* the result; the tool supplies the fact.
- **Recovery from missteps (a graded success metric).** An observation can be a *failure* —
  `pdf_extract` returns garbage, a confidence score is low, a parse doesn't validate. ReAct treats
  that failure as just another observation: the next Thought **re-plans** (try a different tool,
  re-parse, or ask the user) instead of crashing. A prompt-only pipeline has no such join point.

### The Orchestrator = a ReAct planner over sub-agents

Setu's Orchestrator runs ReAct at the *coordination* level. Its "actions" are not only tools but
**dispatching specialized sub-agents**:

> Thought: 4 statements, independent → ingest in parallel.
> Action: dispatch `IngestionAgent` ×4.
> Observation: 3 succeeded, 1 low-confidence on a policy type.
> Thought: route the low-confidence one to a human question; proceed with the other 3.

This is the seam where **reasoning (concept #2)** meets **multi-agent coordination (concept #5)**: one
reasoning loop that delegates to `IngestionAgent`, `ReconciliationAgent`, `InsightsAgent`, observes
their results, and re-plans. Sub-agents keep responsibilities narrow and independently testable;
independent statements run **concurrently**.

---

## 3. LangGraph — the runtime that executes the loop

ReAct is the *pattern*; **LangGraph** is *how Setu runs it reliably*. It models the agent as a
**state machine** — nodes, edges, and one shared state object. Three primitives:

| Primitive | What it is | In Setu (`graph/…`) |
|---|---|---|
| **State** | a `TypedDict` every node reads/writes; flows through the graph | `state.py` — goal, extracted holdings, reconciliation hypotheses, pending `ask_user`. **This is working memory.** |
| **Node** | a function `(state) → partial update`; wraps an agent or tool | `nodes.py` — `ingest`, `reconcile`, `persist`, `ask_user`, `insights` |
| **Edge** | what runs next; **normal** (A→B) or **conditional** (inspect state, pick next) | `build.py` — the conditional edge after `reconcile` is the self-correcting branch |

### What `build.py` does (assemble once, invoke per command)

```python
# graph/build.py (condensed to match the shipped code)
import sqlite3
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

def build_graph(...):
    g = StateGraph(SetuState)                      # 1. State schema (state.py)

    g.add_node("ingest",    nodes.ingest)          # 2. nodes wrap agents/tools
    g.add_node("reconcile", nodes.reconcile)
    g.add_node("replan",    _bump_retries)         #    bounds the self-correction loop
    g.add_node("ask_user",  nodes.ask_user)        #    calls interrupt() internally
    g.add_node("persist",   nodes.persist)

    g.add_edge(START, "ingest")                    # 3. wire edges
    g.add_edge("ingest", "reconcile")
    g.add_conditional_edges(                        #    ← ToT branch AS control flow
        "reconcile", route_after_reconcile,
        {"ok": "persist", "mismatch": "ask_user", "retry": "replan"},
    )
    g.add_edge("replan", "reconcile")               #    bounded loop back
    g.add_edge("ask_user", "persist")
    g.add_edge("persist", END)

    # Checkpointer DB is SEPARATE from the ledger (data/checkpoints.db, not setu.db).
    conn = sqlite3.connect("data/checkpoints.db", check_same_thread=False)
    return g.compile(checkpointer=SqliteSaver(conn))   # 4. durability + HITL
```

`route_after_reconcile` reads the reconciliation status in State and returns `"ok"` / `"mismatch"` /
`"retry"` — the reconciliation decision expressed as a graph edge. `"retry"` routes through a
`replan` node that increments a bounded counter (`MAX_RETRIES`) before looping back, so a persistent
mismatch escalates to the human instead of spinning forever. `cli.py` then does
`graph.invoke(new_state("ingest", path), config={"configurable": {"thread_id": "fidelity_brokerage"}})`.

> **Static vs dynamic interrupt.** The shipped code drives HITL with a *dynamic* `interrupt()` call
> *inside* the `ask_user` node rather than a static `interrupt_before=["ask_user"]` at compile time.
> Both pause+persist the run, but the dynamic form lets the node **compute and attach the question
> payload** (the reconciliation delta, the institution) which `invoke` returns under `__interrupt__`;
> `invoke(Command(resume="accept"))` then continues. Using both at once double-pauses — pick one.

---

## 4. The SQLite checkpointer — durability, resumability, human-in-the-loop

The checkpointer **snapshots State after every node**, keyed by `thread_id`. This one mechanism buys
four things Setu specifically needs:

1. **Durability / resumability.** A multi-statement ingest is long. Crash or Ctrl-C after 3 of 5
   statements → re-invoke with the same `thread_id` and it **resumes from the last checkpoint**; the
   finished statements aren't redone.
2. **Human-in-the-loop (the big one).** The `ask_user` node calls `interrupt({question, …})`, which
   **pauses and persists** the run — `invoke` *returns* with the run frozen in `checkpoints.db` and the
   question payload under `__interrupt__`. The UI shows the question (in Setu today: "reconciliation
   mismatch — accept the extraction anyway?"). Hours — or a process restart — later the user answers and
   you call `graph.invoke(Command(resume="accept"), config=…same thread_id…)` — it continues *exactly*
   where it stopped, State intact, **even from a brand-new process with a fresh connection to the same
   checkpoint file** (verified: `setu ingest` pauses, `setu resume <thread> accept` finishes it).
   **Without the checkpointer a paused run would lose all working memory**, so this is the feature that
   makes the reconciliation interrupt and (later) the ProfilingAgent elicitation possible.
3. **Conversation continuity.** For `setu ask`, reusing the `thread_id` means a follow-up ("what about
   just the India half?") retains prior context — that's **short-term memory** with zero extra code.
4. **Audit / time-travel.** Every step is checkpointed, so the full history of State transitions is
   inspectable — reinforcing the provenance/audit guardrail (concept #6, Week 6).

### Two SQLite databases, two jobs (don't conflate them)

Setu uses SQLite for **two unrelated purposes**, and clarity here is worth a sentence in the report:

| DB | Holds | Memory type | Section |
|---|---|---|---|
| **Checkpointer DB** | run/conversation State per `thread_id` | working + short-term | this week |
| **Ledger DB** | accounts, holdings, balances, FX, obligations (financial truth) | long-term | Week 1 / §2 |

Same engine, different tables, different lifetimes. The checkpointer is *plumbing for the agent's
train of thought*; the ledger is *the source of truth for money*.

---

## 5. Connection to what we build in Week 3

- **`IngestionAgent`** — the first specialized sub-agent: parse → extract → classify → dedup. Proves
  the multi-agent seam (concept #5) with one real member before we add the others.
- **Orchestrator ReAct loop** — Thought/Action/Observation with **visible traces** (published to the
  event bus → Agent Feed, §8). The visible trace is not decoration: it's the concept #2 demo and the
  thing that makes recovery-from-missteps observable.
- **LangGraph skeleton + checkpointer** — `state.py` / `nodes.py` / `build.py` compiled with
  `SqliteSaver`. Even before ToT (Week 4) and RAG (Week 5), the graph runs end-to-end for a single
  statement and is already **durable and resumable**.

> **The Week 3 punchline:** ReAct gives the agent a way to *think, act, observe, and recover*;
> LangGraph + the checkpointer give that loop a *durable, resumable, interruptible runtime*. Reasoning
> without a runtime is a prompt; a runtime without reasoning is a script — Setu needs both.

---

## 6. Further reading (optional)
- Yao et al., 2022 — *ReAct: Synergizing Reasoning and Acting in Language Models*.
- Wei et al., 2022 — *Chain-of-Thought Prompting Elicits Reasoning in LLMs*.
- LangGraph docs — StateGraph, conditional edges, checkpointers, `interrupt`.
- Course Module 3 materials on reasoning architectures and agent control flow.

See `cheatsheet.md` for the one-page recall version.
