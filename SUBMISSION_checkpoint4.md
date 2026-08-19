# Setu: Tree-of-Thought Integration Plan

**CMU Agentic AI Capstone — Checkpoint 4.1**

## Is Tree of Thought appropriate for Setu?

Tree-of-Thought (ToT) reasoning is useful for Setu, but only in one focused part of the system:
reconciling a financial statement when the extracted holdings do not match the total printed on the
statement. Setu combines US and Indian accounts, so statements may use different table layouts,
number formats, currencies, subtotal rows, and policy terms. When totals disagree, there can be
several reasonable explanations: the wrong table column was selected, a subtotal was mistaken for
the account total, a wrapped row was skipped, or a value used Indian digit grouping.

ToT would not help with net-worth calculations, currency conversion, or allocation percentages.
Those are exact operations and remain deterministic Python and SQL tools. It would add cost and make
those steps less reliable. I will therefore use ToT only when extraction creates a genuine ambiguity.

## Where ToT fits in the workflow

Setu already follows this ingestion path:

```text
Statement -> local extraction -> deterministic reconciliation
                                      |
                         totals match | totals differ
                                      |
                              persist | ToT reconciliation
                                              |
                               corrected result or human review
```

A linear chain-of-thought approach can fail here because it commits to one interpretation too early. For example, a
statement might show “Total account value: $262,413.30” and “Total equity: $202,413.30.” If an
extraction accidentally drops a $60,000 holding, choosing the total closest to the extracted sum
would select the equity subtotal and incorrectly declare success. Setu has already been changed to
prefer authoritative labelled totals, but more complex statement errors still require several
complete interpretations to be compared before choosing one.

## ToT structure

A **thought** is one proposed explanation and repair for a mismatch. It includes the chosen stated
total, table boundaries, column mapping, included and excluded rows, currency interpretation, the
resulting holdings, and links to the source lines that support those choices.

A **node** is the current partial reconciliation hypothesis. A **branch** is one alternative decision,
such as selecting a different table, treating a wrapped line as part of the previous holding, or
using a different value column. **Depth** represents the number of repair decisions applied.

The expected branching factor is two to three alternatives per node. Search depth is limited to
three repair decisions, and the beam keeps only the three strongest candidates after each level.
This bounds evaluation to roughly 22 candidates in the worst planned case instead of allowing the
tree to grow without limit.

The search terminates when one branch passes all hard checks, scores at least 85 out of 100, and
leads the next candidate by at least five points. It also stops when the depth or candidate budget is
reached, or when no valid branch remains. If no clear winner exists, Setu pauses and asks the user
rather than guessing.

## Search, evaluation, and pruning

I will use **beam search**. Breadth-first search would keep too many weak candidates, while
depth-first search could spend the budget on one bad interpretation. Monte Carlo sampling would make
results harder to reproduce. Beam search offers a practical middle ground: explore several ideas,
score them at every level, and continue only with the best three.

Each branch receives a score out of 100:

- **50 points — reconciliation:** the repaired holdings match the authoritative stated total within
  the configured 0.5% tolerance.
- **20 points — structural validity:** rows and columns form a consistent table and required values
  are present.
- **15 points — source authority:** explicit labels such as “Total account value” outrank inferred
  totals and subtotals.
- **10 points — coverage:** the branch explains the relevant statement rows without silently
  dropping holdings.
- **5 points — consistency:** currencies, dates, quantities, and signs agree with the rest of the
  statement.

Hard failures are pruned immediately: unknown currency, invalid date, duplicate use of the same row,
negative quantities without supporting text, or unsupported arithmetic. A mismatch lowers a branch's
score but does not prune it before the depth limit, because a later repair may resolve it.
The deterministic reconciliation and validation tools perform the numeric and schema checks. A
CriticAgent reviews the semantic evidence, but it cannot calculate or override a failed financial
constraint. If scores tie, Setu chooses the branch with the stronger source label, fewer repair
assumptions, and then a stable branch ID so repeated runs remain reproducible.

The controller enforces a beam width of three, depth of three, and a fixed candidate budget. ToT is
triggered only after the normal extraction fails reconciliation, so successful statements pay no
extra model cost or latency.

## Roles and implementation tools

| Role | Planned implementation | Responsibility |
|---|---|---|
| Thought generator | **CrewAI** `ReconciliationHypothesisAgent` | Defines the generator role and produces independent repair candidates from redacted structured data and local source snippets. It proposes interpretations but performs no financial math. |
| Critic/evaluator | **CrewAI** critic role plus **LangChain** tools | Reviews evidence and calls deterministic tools for totals, tolerance, schema, coverage, and duplicate-row checks. Tool results dominate the score. |
| Decision maker/controller | **LangChain/LangGraph** | Runs beam search, ranks and prunes branches, enforces budgets, selects the winner, and routes unresolved cases to LangGraph's existing human interrupt. |
| Memory/state manager | **LangGraph checkpointer plus MCP** | LangGraph's SQLite checkpointer remains the authoritative branch state. MCP provides standard access to statement context, validation tools, branch records, and past corrections so generator and critic roles receive the same bounded context. MCP is the context-sharing interface, not the financial ledger. |

This builds on Setu's existing LangGraph state, SQLite checkpointer, ReconciliationAgent, and
accept/reject workflow. The current code generates deterministic total candidates and selects by
source authority; the bounded multi-level search described here is the next implementation step.

## Main risk and mitigation

The most important risk is a **weak evaluation signal pruning the correct branch**. A wrong
extraction can sometimes match a convenient subtotal, so reconciliation error alone is not enough.
Setu reduces this risk by combining the numeric check with source authority, table structure,
coverage, and consistency; keeping three diverse candidates at each level; and requiring a clear
score margin before automatic selection. When the evidence remains close or incomplete, the system
does not force a winner—it preserves the candidates in checkpointed state and asks the user. This
keeps ToT useful as structured exploration without allowing it to turn uncertainty into a confident
financial answer.
