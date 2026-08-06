"""IngestionAgent — parse a statement → extract + classify holdings → account metadata.

Wraps the deterministic `pdf_extract` and the local-model `extract_holdings` (Week 2). It produces
the structured holdings *and* the statement metadata (institution, account ref, period end, file
hash) the graph needs to persist idempotently (§2a). It does not touch the ledger — that's `persist`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from setu.config import Config, load_config
from setu.db import file_sha256
from setu.extraction import ExtractedHolding, extract_holdings
from setu.llm.local import LocalClient
from setu.tools.pdf_extract import ExtractedDoc, extract as pdf_extract


@dataclass
class IngestionResult:
    institution: str
    account_ref: str | None
    period_end: date
    currency: str
    holdings: list[ExtractedHolding]
    file_hash: str
    raw_text: str = field(repr=False, default="")


# Statement date formats we emit in the synthetic PDFs (and common real ones).
_DATE_PATTERNS = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y-%m-%d"),                 # 2026-06-30
    (re.compile(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})"), "%d-%b-%Y"),        # 30-Jun-2026
    (re.compile(r"([A-Za-z]+ \d{1,2}, \d{4})"), "%B %d, %Y"),            # June 30, 2026
]


def _parse_period_end(text: str, fallback: date) -> date:
    """Best-effort extraction of the statement's as-of date; fall back to today's run date."""
    from datetime import datetime

    for pat, fmt in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        raw = m.group(0)
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return fallback


def _guess_institution(text: str, fallback: str) -> str:
    """The institution name is the first non-empty line of the statement in our layouts."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return fallback


_ACCT_RE = re.compile(r"(?:Account|Folio|A/c|Ref)\s+([A-Za-z0-9*\-]+)", re.IGNORECASE)


def _guess_account_ref(text: str) -> str | None:
    m = _ACCT_RE.search(text)
    return m.group(1) if m else None


def _dominant_currency(holdings: list[ExtractedHolding], doc: ExtractedDoc) -> str:
    if holdings:
        # Most common currency among extracted holdings.
        counts: dict[str, int] = {}
        for h in holdings:
            counts[h.currency.upper()] = counts.get(h.currency.upper(), 0) + 1
        return max(counts, key=counts.get)
    return "INR" if ("Rs." in doc.full_text or "₹" in doc.full_text) else "USD"


class IngestionAgent:
    """Parse + extract one statement. Pure read — no ledger writes."""

    def __init__(self, config: Config | None = None, client: LocalClient | None = None):
        self.config = config or load_config()
        self.client = client or LocalClient(self.config)

    def run(self, path: str, run_date: date | None = None) -> IngestionResult:
        doc = pdf_extract(path)
        text = doc.full_text
        result = extract_holdings(text, client=self.client, config=self.config)

        run_date = run_date or date.today()
        return IngestionResult(
            institution=_guess_institution(text, fallback="Unknown"),
            account_ref=_guess_account_ref(text),
            period_end=_parse_period_end(text, fallback=run_date),
            currency=_dominant_currency(result.holdings, doc),
            holdings=result.holdings,
            file_hash=file_sha256(path),
            raw_text=text,
        )
