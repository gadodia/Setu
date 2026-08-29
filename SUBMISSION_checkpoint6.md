# Setu: Safety Guardrails and Human Intervention Plan

**CMU Agentic AI Capstone — Checkpoint 6.1: Safety Guardrails and Human Intervention Plan**

Setu is a local-first financial agent that reads US and Indian statements and insurance documents,
creates a structured ledger, and shows net worth, allocation, coverage, premiums, and supported
policy values. It is read-and-advise only; it does not trade, move money, or submit forms. The main
risks are wrong document classification, missed or duplicated values, OCR or model errors, treating
insurance coverage or a future maturity amount as current wealth, stale FX or reference data,
exposure of personal data, and confident explanations based on weak evidence.

Setu uses several layers of guardrails. At input, the dashboard accepts only PDFs up to 25 MB,
checks the PDF signature, cleans the filename, and deletes temporary uploads after processing. Raw
financial documents use local PDF extraction, Ollama, and local OCR. Account and policy identifiers
are masked before persistence, and raw policy text is excluded from durable workflow checkpoints.
The Claude-facing tool registry exposes only sanitized ledger calculations and portfolio signals;
it has no raw PDF-text or filesystem-path tool.

At processing time, model output must match typed schemas. Financial arithmetic uses Decimal-based
Python and SQL tools, not an LLM. Reconciliation independently compares extracted holdings with the
statement total using a 0.5% tolerance. Insurance rules fail closed: term coverage is not an asset,
and endowment or ULIP value enters net worth only when a current surrender or fund value is
explicitly stated. Unknown currencies fail instead of being guessed. Duplicate files and invalid
review decisions cannot silently create portfolio values. Every saved value keeps source and date
information, and users can deactivate a source without deleting it. The password-protected local
dashboard and request tokens limit access and changes.

Evaluation will use only synthetic or anonymized text and scanned PDFs covering US and Indian
statements, LIC, ULIP, endowment, and term policies. I will measure document-classification
accuracy; exact-match accuracy for critical fields; reconciliation false-accept rate;
unsupported-valuation rate; source and provenance coverage; identifier leakage;
duplicate-handling correctness; OCR fallback and safe-failure rates; review rate and review
precision; and p95 latency for text and scanned documents. Initial targets are at least 95% exact
match on critical fields, zero false acceptance of planted financial conflicts, 100% provenance for
displayed values, zero unsupported values or raw identifiers sent to cloud services, and 100% safe
failure when processing cannot finish. The current suite has 110 passing regression tests. A
repeatable `setu evaluate` runner now checks a synthetic golden corpus. Its latest live-model run
passed 6/6 document classifications, 4/4 reconciliations, 7/7 exact holding extractions, exact net
worth, mismatch escalation, term-policy exclusion, three-horizon risk evaluation, and the cloud
privacy boundary.

Human review is required when totals exceed tolerance, statement text is unavailable, OCR or model
output fails, no usable records are extracted, required policy identity or coverage fields
conflict, valuation evidence is missing or unsupported, currency or source freshness is uncertain,
retrieval has no strong official source, or any future outward action is requested. Incomplete
policy evidence must be rejected; a numeric mismatch may be accepted only after the evidence and
difference are shown.

Together, these controls allow routine, well-supported documents to proceed automatically while
stopping before persistence when risk rises. This adds latency and sometimes asks the user to
review a valid document, but that is preferable to silently adding a wrong financial value. Local
models may be less accurate than cloud models, while deterministic rules are less flexible. Setu
balances this with bounded retries, explicit unknown states, audit records, and human approval.
This supports a staged, dependable single-user deployment without treating model confidence as
financial truth.
