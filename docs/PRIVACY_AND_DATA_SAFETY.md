# Privacy and Data Safety

Setu is a personal capstone project for analyzing US and Indian financial
documents. Financial documents can contain sensitive personal information, so
the public repository and the running application follow different data
boundaries.

## Public repository boundary

The repository contains only source code, public documentation, UI mockups, and
synthetic test/demo data. It must not contain real statements, policy documents,
account numbers, names, addresses, credentials, local databases, or model
checkpoints.

The following runtime artifacts are intentionally ignored by Git:

- `.env` and local credentials
- uploaded documents under `data/inbox/`
- SQLite databases and LangGraph checkpoints
- generated synthetic PDFs and their local ground-truth file
- local model files

Run `uv run setu demo --reset` to regenerate a safe synthetic reviewer dataset.

## Runtime boundary

- Document text is extracted and interpreted locally. Ollama is the optional
  model runtime for local document extraction.
- The Claude explanation loop is separate from ingestion. It receives bounded,
  structured portfolio results through read-only tools; it has no tool that can
  retrieve raw uploaded document text.
- Likely identifiers in a typed question are masked before a Claude request.
- Source records can be deactivated without deleting their audit trail, and
  portfolio totals are recalculated from active sources only.
- Unsupported or uncertain values are excluded from totals and routed to human
  review instead of being guessed.

## Safe use

Use synthetic, anonymized, or publicly available information for demos, issue
reports, screenshots, and evaluation artifacts. Keep personal documents and API
keys only in the local ignored paths. Never paste a secret or real financial
record into a GitHub issue.

Setu is an educational prototype, not a financial adviser. Its calculations and
explanations should be reviewed before they are used for any financial decision.

## Reporting a security issue

Do not disclose a vulnerability with sensitive examples in a public issue. Use
GitHub's private vulnerability reporting or security-advisory workflow for this
repository.
