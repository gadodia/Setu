# Setu: Multi-Agent Architecture and Coordination Plan

**CMU Agentic AI Capstone — Checkpoint 5.1: Multi-Agent Architecture and Coordination Plan**

## Problem and reason for using multiple agents

Setu is designed to help individuals understand financial assets held across the United States and
India. These assets may include brokerage accounts, retirement accounts, mutual funds, bank
accounts, and insurance policies. The system reads financial documents, organizes the information,
checks it for errors, converts values into a common currency, and produces a combined financial
view.

A multi-agent approach is useful because these tasks require different types of reasoning and have
different risks. Document extraction, financial calculations, validation, and research should not
all be handled by one general-purpose agent. Separating these responsibilities makes errors easier
to detect and prevents an incorrect extraction from immediately affecting the user's financial
results.

## Agent roles and responsibilities

Setu will use five agents:

1. **Coordinator Agent:** Manages the workflow and decides which agent should act next. It maintains
   the workflow state, handles failures, and sends uncertain results for human review.
2. **Ingestion Agent:** Reads brokerage statements, bank statements, and insurance documents. It
   uses embedded PDF text when available and local OCR for scanned documents. It converts different
   document layouts into a common structure. Sensitive documents remain local.
3. **Reconciliation Agent:** Independently checks the extracted information. It compares individual
   values with totals shown in the document, verifies required fields, identifies conflicts, and
   prevents unsupported values from being saved. If a result is uncertain, it can ask the Ingestion
   Agent to retry or request human review.
4. **Financial Analysis Agent:** Uses deterministic tools to calculate net worth, currency
   conversions, asset allocation, insurance coverage, premium obligations, and supported maturity
   benefits. The language model does not perform financial arithmetic directly.
5. **Research and Explanation Agent:** Retrieves supporting information from public sources, such as
   official insurance product documents and publicly available financial guidance. It explains
   verified portfolio results in plain language and includes sources and assumptions. It does not
   change ledger values.

## Coordination and communication

Setu will use a hybrid graph-based coordination strategy. The normal path is sequential:

```text
Ingestion -> Reconciliation -> Persistence -> Financial Analysis -> Explanation
```

Conditional paths are used when something goes wrong. For example, missing fields may return to
ingestion, conflicting totals may require another validation pass, and uncertain financial evidence
may pause for human review. The Research and Explanation Agent is called only when external context
is needed.

Agents communicate through structured shared state rather than open-ended conversations. Each
result includes standardized fields, source information, validation status, and warnings. Routine
handoffs are one-way for efficiency. Reconciliation uses two-way communication when a correction or
retry is needed. Only validated information reaches the financial ledger.

## Design trade-offs and scalability

This design improves reliability but adds some latency and coordination work. Additional agents
could increase specialization, but too many would make the system harder to test and understand.
Five agents provide enough separation without unnecessary complexity. The architecture can later
support new agents, such as a form-filling assistant or stock research agent, without changing the
core financial workflow.

Development and demonstrations will use only synthetic, anonymized, or publicly available
information.
