# Setu Design Evolution

Setu did not emerge by implementing every early idea. The final system became smaller, more
deterministic, and more explicit about uncertainty as the project moved from architecture sketches to
financial documents that failed in realistic ways.

## From broad financial assistant to a bounded wealth agent

The first design covered wealth, transactions, reminders, forecasting, and research. The final scope
centers on one problem: consolidate cross-border assets and explain their current evidence-backed
condition. Expense categorization, market forecasting, form filling, and stock research were moved
outside the capstone. This made the success criteria testable: exact net worth, correct source
selection, safe insurance treatment, and visible review when evidence is weak.

## From model arithmetic to a deterministic financial spine

The early concept relied on an LLM to interpret the portfolio and call tools. Implementation made a
hard separation:

- Ollama interprets irregular document text locally.
- Pydantic schemas constrain extracted fields.
- Python `Decimal` and SQL compute every financial result.
- Claude can select approved tools and explain their output, but it cannot write ledger values or
  access raw documents.

This separation made numeric errors observable and gave the project a clear privacy boundary.

## From one statement path to document-specific ingestion

Testing showed that a holdings extractor could not safely represent every financial document. Bank
certificates contain a balance rather than securities, while insurance documents mix coverage,
premiums, projected benefits, and current values. The ingestion path was split into holdings, bank,
and policy handling while retaining one normalized ledger and one LangGraph workflow.

Insurance became the strongest example of the design principle. Term coverage is not wealth;
endowment and LIC savings policies require stated current surrender value; ULIPs require stated fund
value. A policy without a current value is retained as a contract with a valuation gap instead of
being rejected or assigned a guessed amount.

## From planned RAG to deterministic policy rules

Checkpoint 3 proposed a vector store for policy rules, past runs, and user corrections. During the
MVP, the safety-critical rule set proved small and stable enough to encode directly. Semantic
similarity would introduce a new failure mode: retrieving a plausible rule for the wrong policy type.
The final system therefore uses deterministic policy semantics and SQL for exact portfolio facts.

Retrieval remains appropriate future work for cited public reference documents and user notes. It is
not part of the final runtime and cannot override a failed financial validation.

## From full Tree of Thought to bounded hypotheses

Checkpoint 4 proposed a CrewAI generator/critic team, MCP context sharing, and multi-level beam
search. The implemented reconciliation problem did not justify that overhead. Setu instead generates
several independent stated-total hypotheses, ranks them by source authority, performs exact tolerance
checks, retries once, and pauses for a human when the mismatch remains.

This keeps the useful part of structured exploration—comparing alternatives—while making the result
reproducible. It is described as Tree-of-Thought-inspired hypothesis evaluation, not as a full LLM
beam search.

## From a five-agent target to a controlled graph

Checkpoint 5 described five target roles. The final capstone uses fewer active roles:

- An Orchestrator starts and resumes the LangGraph workflow.
- An Ingestion Agent performs local document interpretation.
- A Reconciliation Agent independently validates totals and evidence.
- Deterministic financial tools calculate portfolio facts.
- A separate Claude tool loop optionally explains those facts.

The components exchange typed state and JSON rather than free-form agent conversations. Research and
form-filling remain visible as planned product extensions, not implemented agents.

## From a portfolio inventory to decision support

The first dashboard mainly answered “what do I own?” Final-demo work added source-backed cost basis,
unrealized gain and ROI, concentration, currency exposure, target-allocation drift, known premium
obligations, short- and long-term risk, an explainable health score, missing-data disclosure, and
bounded review actions.

The user can also deactivate a source without deleting it. Every affected calculation updates from
the remaining active evidence, turning provenance into a practical control rather than a passive
audit field.

## From safety intentions to enforced boundaries

The final system implements the Module 6 controls in code:

- Local raw-document processing and optional local OCR.
- Masked identifiers and no raw document tool in the Claude registry.
- Project-local personal API credentials pinned to Anthropic's official endpoint.
- Typed validation, Decimal arithmetic, reconciliation, and fail-closed policy valuation.
- Duplicate detection and source-linked persistence.
- Password-protected local dashboard.
- Durable human review for unresolved mismatches.
- No trade, payment, or form-submission tools.

The resulting architecture is less ambitious than some checkpoint plans, but more cohesive and
defensible: probabilistic components interpret and explain, deterministic components protect
financial truth, and the user remains responsible for uncertain or consequential decisions.
