# Week 3 — Adversarial review findings (to fix next session)

An adversarial review workflow (3 review dimensions → independent verifiers) ran over the Week 3
graph code. **4 confirmed real defects + 1 false positive.** The code is functional and all 39
tests pass; these are correctness/robustness gaps to address before Week 4 relies on them.

Ranked most-severe first.

## 1. [HIGH] persist creates a NEW Account per statement → net-worth inflation across periods
- **Where:** `setu/graph/nodes.py` (persist node, ~L182–193); `setu/models/entities.py` Account (no
  unique constraint); `setu/tools/calc.py:122` sums over all positions.
- **Bug:** `persist` always constructs a new `Institution` + `Account` and adds them. The only
  idempotency guard is the `file_hash` short-circuit, which fires *only* for byte-identical
  re-ingests. The `Statement` UniqueConstraint is `(institution, account_ref, period_end)` — blocks
  re-ingesting the *same* period, but a **new period** (July after June) for the same real account
  creates a *second* Account row. `_latest_by_account` (calc.py:58) keys on `account_id`, so the new
  account doesn't supersede the old snapshot — both are summed → **net worth inflates over time.**
- **Fix:** get-or-create Account/Institution by natural key (institution name + account_ref +
  account_type) instead of always inserting. Consider a UniqueConstraint on Account
  `(institution_id, account_ref)`.

## 2. [HIGH] Reconciliation is not an independent check — min-distance selection defeats it
- **Where:** `setu/agents/reconciliation_agent.py:86` (`best = min(cands, key=lambda c: abs(c.value - sum_extracted))`).
- **Bug:** the "stated total" is chosen as whichever candidate is numerically **closest to the very
  sum being verified.** So the verifier picks the hypothesis that best agrees with the extraction —
  a wrong extraction that happens to match a subtotal line reconciles as `ok`. Reproduced: statement
  with "Total account value: $262,413.30" + "Total equity: 202,413.30"; extraction drops a $60k
  holding → sum = 202,413.30 → picks the 202,413.30 subtotal → spurious `ok`.
- **Fix:** select the stated total by **authority/parse rule** (prefer the explicit labelled
  "Total account value" line), not by closeness to the sum. Only then compare to the extracted sum.

## 3. [MEDIUM] H2 "table-total-row" regex captures non-total figures as equal candidates
- **Where:** `setu/agents/reconciliation_agent.py:67` (`re.finditer(r"\bTotal\b[^0-9]*(NUM)")`).
- **Bug:** matches "Total shares: 1,995"→1995, "Total fees 200.00"→200, and because `[^0-9]*` spans
  newlines, a bare "Total" header grabs the first number many lines below (e.g. an account number).
  These become equal-standing candidates, feeding the min-distance bug (#2).
- **Fix:** tighten the regex (anchor to currency-prefixed amounts / same-line), and/or drop H2 once
  #2 selects by authority.

## 4. [MEDIUM] `_raw_text` cache is lost on a fresh-process resume → reconcile could pass empty text
- **Where:** `setu/graph/nodes.py:71` (`self._raw_text`, per-instance, NOT in SetuState).
- **Bug:** `_raw_text` is populated only in `ingest` and is not part of the serialized State, so the
  checkpointer never snapshots it. If a run ever re-enters `reconcile` in a fresh process (empty
  cache), `_candidates("")` returns `[]` → `status="ok", delta=0` → persists unverified holdings.
  **Currently latent:** the normal HITL resume path goes `ask_user → persist` (never back through
  `reconcile`), so it doesn't trigger today — but the `retry → replan → reconcile` loop after a
  cross-process resume could. Fragile.
- **Fix:** carry the statement text (or the parsed candidate totals) in `SetuState` so reconcile is
  self-contained and checkpoint-durable, rather than relying on instance-cached text.

## Not a bug (verified false positive)
- **account_type hardcoded to BROKERAGE** (`nodes.py:189`): real, but no downstream reader keys off
  `Account.account_type` — `compute_net_worth` uses only asset_class/geography/currency. No net-worth
  or categorization harm today. Worth fixing for correctness later (classification week), not urgent.
