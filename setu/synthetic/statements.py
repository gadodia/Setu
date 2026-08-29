"""Render the canonical synthetic portfolio as realistic PDF statements.

Each institution produces a differently-formatted document — mirroring the real-world pain Setu
solves: incompatible layouts across US brokerage, Indian CAS, bank, and insurance statements.
The numbers come from `spec.PORTFOLIO`, so a parsed statement reconciles to the seeded ledger.

These are synthetic — masked account refs only, no real PII.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from setu.config import Config, load_config
from setu.models import AccountType
from setu.synthetic.spec import AS_OF, PORTFOLIO, AccountSpec

_STYLES = getSampleStyleSheet()


def _fmt(amount: Decimal, currency: str) -> str:
    sym = {"USD": "$", "INR": "Rs. "}.get(currency.upper(), "")
    return f"{sym}{amount:,.2f}"


def _table(data: list[list[str]], col_widths=None) -> Table:
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _brokerage_story(acct: AccountSpec) -> list:
    """US brokerage / 401k layout with source-stated cost basis."""
    story = [
        Paragraph(f"<b>{acct.institution}</b>", _STYLES["Title"]),
        Paragraph(f"{acct.account_name} &nbsp;&nbsp; Account {acct.account_ref}", _STYLES["Normal"]),
        Paragraph(f"Statement period ending {AS_OF.strftime('%B %d, %Y')}", _STYLES["Normal"]),
        Spacer(1, 0.25 * inch),
        Paragraph("<b>Holdings</b>", _STYLES["Heading2"]),
    ]
    rows = [["Symbol", "Description", "Quantity", "Cost Basis", "Market Value"]]
    total = Decimal("0")
    for h in acct.holdings:
        rows.append([
            h.symbol or "-",
            h.name,
            f"{h.quantity:,.3f}",
            _fmt(h.cost_basis, h.currency),
            _fmt(h.market_value, h.currency),
        ])
        total += h.market_value
    rows.append(["", "", "", "Total", _fmt(total, acct.currency)])
    story.append(_table(
        rows,
        col_widths=[0.7 * inch, 2.05 * inch, 0.8 * inch, 1.3 * inch, 1.35 * inch],
    ))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        f"Total account value: <b>{_fmt(total, acct.currency)}</b> as of {AS_OF.isoformat()}.",
        _STYLES["Normal"]))
    return story


def _cas_story(acct: AccountSpec) -> list:
    """Indian mutual-fund CAS layout with source-stated invested amount."""
    story = [
        Paragraph("<b>Consolidated Account Statement (CAS)</b>", _STYLES["Title"]),
        Paragraph(f"{acct.institution} &nbsp;&nbsp; Folio {acct.account_ref}", _STYLES["Normal"]),
        Paragraph(f"As on {AS_OF.strftime('%d-%b-%Y')}", _STYLES["Normal"]),
        Spacer(1, 0.25 * inch),
        Paragraph("<b>Mutual Fund Holdings</b>", _STYLES["Heading2"]),
    ]
    rows = [["Scheme Name", "Units", "Invested Amount", "NAV", "Current Value"]]
    total = Decimal("0")
    for h in acct.holdings:
        nav = (h.market_value / h.quantity) if h.quantity else Decimal("0")
        rows.append([
            h.name,
            f"{h.quantity:,.3f}",
            f"{h.cost_basis:,.2f}",
            f"{nav:,.4f}",
            f"{h.market_value:,.2f}",
        ])
        total += h.market_value
    rows.append(["", "", "", "Total", f"{total:,.2f}"])
    story.append(_table(
        rows,
        col_widths=[2.2 * inch, 0.8 * inch, 1.25 * inch, 0.8 * inch, 1.15 * inch],
    ))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        f"Portfolio valuation: <b>Rs. {total:,.2f}</b> as on {AS_OF.strftime('%d-%b-%Y')}.",
        _STYLES["Normal"]))
    return story


def _bank_story(acct: AccountSpec) -> list:
    """Bank statement layout: closing balance figure."""
    return [
        Paragraph(f"<b>{acct.institution}</b>", _STYLES["Title"]),
        Paragraph(f"{acct.account_name} Account &nbsp;&nbsp; A/c {acct.account_ref}", _STYLES["Normal"]),
        Paragraph(f"Statement as on {AS_OF.strftime('%d-%b-%Y')}", _STYLES["Normal"]),
        Spacer(1, 0.25 * inch),
        _table([
            ["Description", "Amount (Rs.)"],
            ["Closing Balance", f"{acct.balance:,.2f}"],
        ], col_widths=[3.5 * inch, 1.8 * inch]),
        Spacer(1, 0.2 * inch),
        Paragraph(f"Available balance: <b>Rs. {acct.balance:,.2f}</b>.", _STYLES["Normal"]),
    ]


def _insurance_story(acct: AccountSpec) -> list:
    """Insurance statement: policy type + the right value figure per type (§5b)."""
    story = [
        Paragraph(f"<b>{acct.institution}</b>", _STYLES["Title"]),
        Paragraph(f"Policy Statement &nbsp;&nbsp; Ref {acct.account_ref}", _STYLES["Normal"]),
        Paragraph(f"As on {AS_OF.strftime('%d-%b-%Y')}", _STYLES["Normal"]),
        Spacer(1, 0.25 * inch),
    ]
    rows = [["Policy", "Type", "Sum Assured", "Current Value", "Annual Premium", "Next Due"]]
    for p in acct.policies:
        sa = f"{p.sum_assured:,.2f}" if p.sum_assured else "-"
        if p.policy_type.value == "TERM":
            val = "N/A (protection)"
        elif p.asset_value is None:
            val = "Not stated"
        else:
            val = f"{p.asset_value:,.2f}"
        premium = f"{p.premium_amount:,.2f}" if p.premium_amount else "-"
        due = p.premium_due_date.strftime("%d-%b-%Y") if p.premium_due_date else "-"
        rows.append([p.name, p.policy_type.value, sa, val, premium, due])
    story.append(_table(rows, col_widths=[1.75 * inch, 0.65 * inch, 1.05 * inch,
                                         1.15 * inch, 1.05 * inch, 1.0 * inch]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "ULIP fund value is market-linked (units x NAV). Term plans provide protection only "
        "and carry no surrender/asset value. A missing endowment surrender value is unknown, "
        "not zero, until a current value statement is supplied.", _STYLES["Normal"]))
    return story


def _story_for(acct: AccountSpec) -> list:
    if acct.account_type in (AccountType.BROKERAGE, AccountType.RETIREMENT_401K):
        return _brokerage_story(acct)
    if acct.account_type == AccountType.MF_FOLIO:
        return _cas_story(acct)
    if acct.account_type == AccountType.BANK:
        return _bank_story(acct)
    if acct.account_type == AccountType.INSURANCE:
        return _insurance_story(acct)
    raise ValueError(f"No statement renderer for {acct.account_type}")


def _slug(acct: AccountSpec) -> str:
    inst = acct.institution.split("(")[0].strip().lower().replace(" ", "_")
    typ = acct.account_type.value.lower()
    return f"{inst}_{typ}.pdf"


def generate_statements(config: Config | None = None) -> list[Path]:
    """Render every account in the portfolio to a PDF in the synthetic dir. Returns the paths."""
    config = config or load_config()
    out_dir = config.paths.synthetic_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for acct in PORTFOLIO:
        path = out_dir / _slug(acct)
        doc = SimpleDocTemplate(str(path), pagesize=letter,
                                topMargin=0.7 * inch, bottomMargin=0.7 * inch)
        doc.build(_story_for(acct))
        paths.append(path)
    return paths
