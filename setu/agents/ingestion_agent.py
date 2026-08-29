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
from setu.extraction import (
    DocumentKind,
    ExtractedBalance,
    ExtractedHolding,
    ExtractedPolicy,
    detect_document_kind,
    detect_policy_document_type,
    extract_balance,
    extract_holdings,
    extract_policies,
)
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
    document_kind: DocumentKind = "HOLDINGS"
    policies: list[ExtractedPolicy] = field(default_factory=list)
    policy_document_type: str = "UNKNOWN"
    balance: ExtractedBalance | None = None


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


def _guess_institution(
    text: str,
    fallback: str,
    document_kind: DocumentKind = "HOLDINGS",
) -> str:
    """The institution name is the first non-empty line of the statement in our layouts."""
    known_institutions = (
        "HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank", "Kotak Mahindra Bank",
        "Fidelity", "CAMS", "LIC of India", "Tata AIA",
    )
    for institution in known_institutions:
        if institution.lower() in text.lower():
            return institution
    if document_kind == "BANK":
        compact = re.sub(r"[^a-z]", "", text.lower())
        if "balanceconfirmationcertificate" in compact:
            return "Bank balance certificate"
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return fallback


_ACCT_RE = re.compile(
    r"(?:Account|Folio|A/c|Ref|Policy\s+(?:Number|No\.?|Ref))\s*[:#-]?\s*([A-Za-z0-9*\-]+)",
    re.IGNORECASE,
)


def _guess_account_ref(
    text: str,
    tables: list[list[list[str | None]]] | None = None,
) -> str | None:
    for table in tables or []:
        if len(table) < 2:
            continue
        account_index = next(
            (
                index
                for index, cell in enumerate(table[0])
                if "accountnumber" in re.sub(r"[^a-z]", "", (cell or "").lower())
            ),
            None,
        )
        if account_index is None:
            continue
        for row in table[1:]:
            if account_index >= len(row):
                continue
            match = re.search(r"(?<!\d)(\d[\d -]{5,}\d)(?!\d)", row[account_index] or "")
            if match:
                digits = re.sub(r"\D", "", match.group(1))
                return f"****{digits[-4:]}"
    m = _ACCT_RE.search(text)
    if not m:
        return None
    value = m.group(1)
    if value.lower() in {"number", "no", "title", "type"}:
        return None
    return value if value.startswith("****") else f"****{value[-4:]}"


def _dominant_currency(
    holdings: list[ExtractedHolding],
    doc: ExtractedDoc,
    policies: list[ExtractedPolicy] | None = None,
    balance: ExtractedBalance | None = None,
) -> str:
    if balance is not None:
        return balance.currency.upper()
    if holdings:
        # Most common currency among extracted holdings.
        counts: dict[str, int] = {}
        for h in holdings:
            counts[h.currency.upper()] = counts.get(h.currency.upper(), 0) + 1
        return max(counts, key=counts.get)
    if policies:
        counts: dict[str, int] = {}
        for policy in policies:
            counts[policy.currency.upper()] = counts.get(policy.currency.upper(), 0) + 1
        return max(counts, key=counts.get)
    return "INR" if ("Rs." in doc.full_text or "₹" in doc.full_text) else "USD"


class IngestionAgent:
    """Parse + extract one statement. Pure read — no ledger writes."""

    def __init__(self, config: Config | None = None, client: LocalClient | None = None):
        self.config = config or load_config()
        self.client = client or LocalClient(self.config)

    def run(self, path: str, run_date: date | None = None) -> IngestionResult:
        ocr = self.config.ocr
        doc = pdf_extract(
            path,
            ocr_mode=ocr.mode if ocr.enabled else "never",
            min_text_chars=ocr.min_text_chars,
            ocr_dpi=ocr.dpi,
            ocr_pipeline_version=ocr.pipeline_version,
        )
        text = doc.full_text
        document_kind = detect_document_kind(text)
        if document_kind == "POLICY":
            policy_document_type = detect_policy_document_type(text)
            policy_result = extract_policies(text, client=self.client, config=self.config)
            policies = policy_result.policies
            holdings: list[ExtractedHolding] = []
            balance = None
        elif document_kind == "BANK":
            policy_document_type = "UNKNOWN"
            policies = []
            holdings = []
            balance = extract_balance(text, doc.all_tables)
        else:
            policy_document_type = "UNKNOWN"
            holding_result = extract_holdings(text, client=self.client, config=self.config)
            holdings = holding_result.holdings
            policies = []
            balance = None

        run_date = run_date or date.today()
        return IngestionResult(
            institution=_guess_institution(text, fallback="Unknown", document_kind=document_kind),
            account_ref=_guess_account_ref(text, doc.all_tables),
            period_end=_parse_period_end(text, fallback=run_date),
            currency=_dominant_currency(holdings, doc, policies, balance),
            holdings=holdings,
            file_hash=file_sha256(path),
            raw_text=text,
            document_kind=document_kind,
            policies=policies,
            policy_document_type=policy_document_type,
            balance=balance,
        )
