# Future simplification notes

This note captures usability and architecture improvements to revisit after the capstone checkpoints.
It is not part of the current implementation plan.

## 1. Hide development infrastructure from users

A normal user should only need commands such as:

```bash
setu ingest policy.pdf
setu report
```

Setu should hide or automate:

- `uv` and optional dependency groups
- Python virtual-environment activation
- PaddleOCR and Ollama startup checks
- LangGraph thread identifiers
- checkpoint and database locations

Possible approaches include a `setu setup` command, a small launcher, automatic thread generation,
and friendlier health/status diagnostics.

## 2. Use declarative files for agent behavior

Move behavior that does not require executable enforcement into Markdown or YAML:

- agent roles and responsibilities
- prompts and reasoning guidance
- workflow descriptions
- tool-selection guidance
- policy terminology and product knowledge
- examples and human-review instructions

Potential structure:

```text
agents/
  ingestion.md
  reconciliation.md
  portfolio_advisor.md
knowledge/
  policy_rules.yaml
prompts/
  policy_extraction.md
  holdings_extraction.md
```

This would make agent behavior easier to understand and revise without changing Python modules.

## 3. Keep enforceable behavior in Python

Python should remain responsible for behavior that must be deterministic, testable, or secure:

- exact Decimal arithmetic and currency conversion
- TERM, endowment, and ULIP valuation guardrails
- schema validation and date parsing
- OCR/PDF adapters and local-model calls
- database persistence and idempotency
- privacy boundaries and secret handling
- checkpointing and human-review control flow

The design principle remains: declarative files explain what the agent should do; executable code
enforces what the system must never get wrong.

## 4. Revisit after the working workflow stabilizes

Before refactoring, observe several real CLI runs and record which implementation details confuse
users. Then simplify the interface without weakening financial validation, privacy, provenance, or
test coverage.
