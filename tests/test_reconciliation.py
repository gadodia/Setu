"""ReconciliationAgent — the independent check must stay independent (Week 3 review #2, #7).

The reconciliation verdict is Setu's primary feedback signal, so its selection of the "stated
total" must not be influenced by the very extraction it is meant to verify. These tests pin the
two review fixes:
  #2 — select the stated total by AUTHORITY (labelled line first), never by closeness to the sum.
  #7 — the "Total" row regex must not capture non-currency figures (share counts, account numbers).
"""

from __future__ import annotations

from decimal import Decimal

from setu.agents.reconciliation_agent import ReconciliationAgent


def _agent(config) -> ReconciliationAgent:
    return ReconciliationAgent(config)


def test_labelled_total_wins_over_a_closer_subtotal(config):
    """#2: a wrong extraction that matches a subtotal must NOT reconcile as ok.

    The labelled "Total account value" is 262,413.30; a "Total equity" subtotal is 202,413.30.
    Extraction dropped a $60k holding, so the sum (202,413.30) exactly equals the subtotal. Selecting
    by closeness would pick the subtotal and report ok; selecting by authority picks the labelled
    total and correctly reports a mismatch.
    """
    text = (
        "Fidelity Investments — Account Statement\n"
        "Total account value: $262,413.30\n"
        "Total equity: $202,413.30\n"
    )
    res = _agent(config).run(text, sum_extracted=Decimal("202413.30"))

    assert res.stated_total == Decimal("262413.30")
    assert res.status == "mismatch"


def test_labelled_total_matching_sum_reconciles_ok(config):
    """A correct extraction still reconciles against the authoritative labelled total."""
    text = "Total account value: $262,413.30\nTotal equity: $202,413.30\n"
    res = _agent(config).run(text, sum_extracted=Decimal("262413.30"))

    assert res.stated_total == Decimal("262413.30")
    assert res.status == "ok"


def test_total_row_regex_ignores_share_counts_and_account_numbers(config):
    """#7: 'Total shares: 1,995' and a bare 'Total' header near an account number are not totals.

    With no currency-prefixed labelled line, the only currency figure is the $115,000.00 holdings
    total, which the tightened regex should pick — not the share count or the account number.
    """
    text = (
        "Account #: 1234567890\n"
        "Total shares: 1,995\n"
        "Holding A          $60,000.00\n"
        "Holding B          $55,000.00\n"
        "Total               $115,000.00\n"
    )
    res = _agent(config).run(text, sum_extracted=Decimal("115000.00"))

    assert res.stated_total == Decimal("115000.00")
    assert res.status == "ok"


def test_no_total_present_reconciles_ok_with_none(config):
    """No stated total anywhere → can't disconfirm → ok with stated_total None (unchanged behavior)."""
    text = "Some statement with no recognizable total line at all.\n"
    res = _agent(config).run(text, sum_extracted=Decimal("115000.00"))

    assert res.stated_total is None
    assert res.status == "ok"
