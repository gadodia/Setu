# Week 3 — Adversarial review findings (to fix next session)

An adversarial review workflow (3 review dimensions → independent verifiers, 15 agents) ran over the
Week 3 graph code. **12 raised → 9 confirmed real defects** (verifiers refuted 3 as false positives).
The code is functional and all 39 tests pass; these are correctness/robustness gaps to address
before Week 4 relies on them. Ranked by severity.

---

## CRITICAL

### 1. reconcile reads raw text from a non-checkpointed instance cache → empty on resume → silent bad persist  ✅ FIXED (2026-08-07)
- **Fix landed:** `raw_text` now carried in `SetuState` (`ingest` returns it, `reconcile` reads
  `state.get("raw_text")`); the `Nodes._raw_text` instance cache is gone. `reconcile` also escalates
  to `mismatch` (not silent `ok`) when text is unavailable but holdings are present. Regression:
  `tests/test_graph_ingest.py::test_reconcile_with_lost_text_escalates_instead_of_silently_persisting`.

- **Where:** `setu/graph/nodes.py:105` (reads `self._raw_text`); cache at `nodes.py:71`, populated only in `ingest` (`nodes.py:79`).
- **Bug:** `_raw_text` lives on the `Nodes` instance, NOT in `SetuState`, so the checkpointer never
  snapshots it. If the process dies after `ingest` checkpoints but before `reconcile` completes, a
  fresh process (new `Nodes`, empty `_raw_text`) resumes and re-runs `reconcile` with `text=""` →
  `_candidates("")` returns `[]` → `status="ok", stated_total=None, delta=0` → routes to `persist`.
  A statement whose real total does NOT match the extracted sum is silently persisted as reconciled.
  **Not triggered by the normal accept/reject resume** (that path is `ask_user → persist`, never
  re-enters reconcile) — only by crash-recovery / cross-process resume that re-runs reconcile.
- **Fix:** carry `raw_text` (or better, the derived `stated_total`/candidate totals) in `SetuState`;
  `ingest` returns it, `reconcile` reads `state.get(...)`. Also: distinguish "no total in document"
  from "text unavailable" — don't treat empty text as automatic `ok` when holdings are present.

### 2. Reconciliation picks the candidate closest to the extracted sum → defeats the independent check  ✅ FIXED (2026-08-07)
- **Fix landed:** `TotalHypothesis` gained an `authority` rank (0 labelled > 1 table-total > 2
  largest-figure); `run()` selects `min(cands, key=(authority, -value))` — by authority, never by
  closeness to the sum. Regression: `tests/test_reconciliation.py::test_labelled_total_wins_over_a_closer_subtotal`.

- **Where:** `setu/agents/reconciliation_agent.py:86` (`best = min(cands, key=lambda c: abs(c.value - sum_extracted))`).
- **Bug:** the "stated total" is chosen as whichever candidate is numerically closest to the sum
  being verified, so the verifier picks the hypothesis that best agrees with the extraction. A wrong
  extraction matching a subtotal line reconciles as `ok`. Reproduced: "Total account value:
  $262,413.30" + "Total equity: 202,413.30"; extraction drops a $60k holding → sum=202,413.30 →
  picks the subtotal → spurious `ok`.
- **Fix:** select the stated total by **authority/parse rule** (prefer the explicit labelled "Total
  account value" line), not by closeness to the sum. Only then compare to the extracted sum.

---

## HIGH

### 3. persist creates a NEW Institution + Account per statement → duplicate accounts, double-counted net worth
- **Where:** `setu/graph/nodes.py:182`; Account has no unique constraint (`entities.py:73–87`); `calc.py:122` sums all positions.
- **Bug:** always inserts a new Account. A **new period** (July after June) for the same real account
  creates a second `account_id`, which `_latest_by_account` (calc.py:58, keys on account_id) does NOT
  supersede → both summed → **net worth inflates over time.**
- **Fix:** get-or-create Institution/Account by natural key (name + account_ref + type). Consider a
  UniqueConstraint on Account `(institution_id, account_ref)`.

### 4. Hash-only idempotency inconsistent with uq_statement_period → uncaught IntegrityError
- **Where:** `setu/graph/nodes.py:159` (checks only `file_hash`); `Statement` UniqueConstraint is `(institution, account_ref, period_end)` (`entities.py:203`); commit at `nodes.py:210`.
- **Bug:** a corrected/re-exported statement for the same period has different bytes → different hash
  → `already_ingested` False → persist proceeds → commit violates `uq_statement_period` → uncaught
  `IntegrityError`, node crashes (no try/except/rollback).
- **Fix:** in persist, also query by the logical key `(institution, account_ref, period_end)` before
  adding; if present, treat as idempotent skip (or explicit "corrected restatement" path). Wrap
  commit with rollback handling.

### 5. resume on unknown/never-paused thread_id → KeyError('statement_path') instead of graceful message
- **Where:** `setu/agents/orchestrator.py:69` → `nodes.ingest` `state["statement_path"]` (`nodes.py:74`).
- **Bug:** `setu resume wrong-thread accept` (typo / never-paused) finds no checkpoint → LangGraph
  starts a NEW run from START; `Command(resume=...)` supplies no initial state → `ingest` hits
  `state["statement_path"]` → `KeyError`. Verified empirically.
- **Fix:** in `Orchestrator.resume`, `get_state(cfg)` first; if `snapshot.created_at is None or not
  snapshot.next`, return a clean "no paused run for thread X" outcome instead of invoking.

---

## MEDIUM

### 6. Bounded retry loop can never change the verdict (dead control flow)
- **Where:** `setu/graph/build.py:44` (retry branch), `_bump_retries` (`build.py:49–58`), edge `build.py:111`.
- **Bug:** `replan` only increments `retries` + appends a trace event; it mutates neither `extracted`
  nor text. `reconcile` is pure deterministic math over those inputs, so the second pass is identical
  → always re-escalates to `ask_user`. The retry burns one wasted reconcile call + emits a misleading
  "re-planning" trace on every mismatch.
- **Fix:** either make `replan` feed something back (re-extract with different params → genuine
  self-correction), or delete the retry branch and route `mismatch` straight to `ask_user`.

### 7. H2 "Total" regex captures non-total figures → junk candidates for the min-distance scorer  ✅ FIXED (2026-08-07)
- **Fix landed:** H2 regex now anchors to a currency-prefixed amount on the same line
  (`\bTotal\b[^\n]*?(?:Rs\.?|\$|₹)\s*NUM`), so "Total shares: 1,995" and bare-header→far-number no
  longer match. Regression: `tests/test_reconciliation.py::test_total_row_regex_ignores_share_counts_and_account_numbers`.

- **Where:** `setu/agents/reconciliation_agent.py:67` (`re.finditer(r"\bTotal\b[^0-9]*(NUM)")`).
- **Bug:** matches "Total shares: 1,995"→1995, "Total fees 200.00"→200; `[^0-9]*` spans newlines so a
  bare "Total" header grabs a number many lines below (e.g. account number). These equal-standing
  candidates feed the min-distance bug (#2).
- **Fix:** tighten regex (anchor to currency-prefixed amounts / same line); likely moot once #2
  selects by authority.

### 8. Re-ingesting same file re-runs whole graph + duplicates trace (default thread_id = file stem)
- **Where:** `setu/graph/state.py:79` (`_append` reducer); CLI default thread `cli.py:143`.
- **Bug:** `trace` reducer concatenates across separate invokes sharing a thread_id. CLI defaults
  thread to `p.stem`, so `setu ingest fidelity.pdf` twice replays from START (re-parses PDF,
  re-calls the local model — wasted) and re-appends trace on top of the checkpoint's existing trace
  → doubled Thought/Action/Observation output. Verified empirically.
- **Fix:** in `Orchestrator.ingest`, `get_state(cfg)` first; if a completed checkpoint exists (no
  `next`), return the stored outcome or raise "already ingested under thread X; pass a new --thread".

---

## LOW

### 9. persist treats any resume decision except exact 'reject' as acceptance (fail-open)
- **Where:** `setu/graph/nodes.py:152` (only special-cases `user_decision == "reject"`).
- **Bug:** `Command(resume='no'/'cancel'/'r'/typo/None)` → not exactly `"reject"` → falls through to
  persisting all holdings. A statement the user meant to reject gets written.
- **Fix:** fail-safe — key off the human path: `decision = state.get("user_decision"); if decision is
  not None and decision != "accept": <persist nothing>`. (The reconciled `ok` path reaches persist
  with `user_decision=None` and must still persist.)

---

## Verified FALSE POSITIVES (not bugs — do not act)
- **account_type hardcoded to BROKERAGE** (`nodes.py:189`): real, but no downstream reader keys off
  `Account.account_type` (`compute_net_worth` uses only asset_class/geography/currency). No harm
  today; tidy up in the classification week.
- (2 other raised items refuted by verifiers — see workflow journal `wf_b7761b71-62b` if needed.)
