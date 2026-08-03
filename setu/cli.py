"""Setu command-line interface.

Week 1 commands operate on the deterministic substrate only:
  setu init-db   create the SQLite schema
  setu seed      generate the synthetic US+India portfolio (+ ground-truth fixture)
  setu report    print net worth + allocation (USD base)
  setu ingest    [stub — Week 2+]  parse real statements
  setu ask       [stub — Week 7]   Q&A over the portfolio
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from setu.config import load_config
from setu.db import create_all, drop_all, get_session
from setu.tools import calc

app = typer.Typer(help="Setu — cross-border wealth & portfolio agent.", no_args_is_help=True)
console = Console()


def _money(amount: Decimal, currency: str) -> str:
    q = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sym = {"USD": "$", "INR": "₹"}.get(currency.upper(), "")
    return f"{sym}{q:,.2f}"


def _pct(fraction: Decimal) -> str:
    return f"{(Decimal(fraction) * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


@app.command("init-db")
def init_db(fresh: bool = typer.Option(False, "--fresh", help="Drop and recreate all tables.")):
    """Create the SQLite schema."""
    config = load_config()
    if fresh:
        drop_all(config)
    create_all(config)
    console.print(f"[green]Schema ready[/green] at {config.paths.db_path}")


@app.command()
def seed(
    fresh: bool = typer.Option(True, "--fresh/--no-fresh", help="Recreate tables first."),
    pdfs: bool = typer.Option(True, "--pdfs/--no-pdfs", help="Also render synthetic PDF statements."),
):
    """Generate the synthetic US+India portfolio, ground-truth fixture, and PDF statements."""
    from setu.synthetic.generate import seed_portfolio, write_ground_truth
    from setu.synthetic.statements import generate_statements

    config = load_config()
    if fresh:
        drop_all(config)
    create_all(config)
    with get_session(config) as session:
        seed_portfolio(session, config)
    gt = write_ground_truth(config)
    console.print("[green]Seeded synthetic portfolio.[/green]")
    console.print(f"Ground truth written; net worth = {_money(Decimal(gt['total']), config.base_currency)}")

    if pdfs:
        paths = generate_statements(config)
        console.print(f"[green]Rendered {len(paths)} PDF statements[/green] in {config.paths.synthetic_dir}")


@app.command()
def report():
    """Print net worth + asset allocation (by class, geography, currency)."""
    config = load_config()
    with get_session(config) as session:
        nw = calc.compute_net_worth(session, config)

    if nw.total == 0:
        console.print("[yellow]Ledger is empty.[/yellow] Run [bold]setu seed[/bold] first.")
        raise typer.Exit(code=0)

    base = config.base_currency
    console.print(f"\n[bold]NET WORTH:[/bold] {_money(nw.total, base)}  [dim]({base} base)[/dim]\n")

    _alloc_table("Asset allocation", nw.by_asset_class, nw, base)
    _alloc_table("By geography", nw.by_geography, nw, base)
    _alloc_table("By currency", nw.by_currency, nw, base)


def _alloc_table(title: str, buckets: dict, nw: calc.NetWorth, base: str):
    alloc = nw.allocation(buckets)
    table = Table(title=title, title_style="bold cyan", show_edge=False)
    table.add_column("Bucket")
    table.add_column("Value", justify="right")
    table.add_column("Share", justify="right")
    for key in sorted(buckets, key=lambda k: buckets[k], reverse=True):
        table.add_row(key, _money(buckets[key], base), _pct(alloc[key]))
    console.print(table)
    console.print()


@app.command()
def ingest(path: str = typer.Argument(..., help="Path to a PDF statement.")):
    """Extract holdings from a PDF statement (Week 2: parse + local-model extraction).

    Runs the deterministic pdf_extract, then the LOCAL model to produce structured holdings.
    Persistence + reconciliation against the stated total arrive in Week 4; for now this shows
    what was extracted so the parse quality is inspectable.
    """
    from setu.extraction import extract_from_pdf
    from setu.llm.local import LocalClient, LocalModelError

    config = load_config()
    p = Path(path)
    if not p.exists():
        console.print(f"[red]No such file:[/red] {path}")
        raise typer.Exit(code=1)

    client = LocalClient(config)
    if not client.available():
        console.print(
            f"[red]Local model '{client.model}' not reachable at {config.ollama.host}.[/red]\n"
            "Start Ollama (`ollama serve`) and pull the model (`ollama pull "
            f"{client.model}`), or change model_router.extraction in config.yaml."
        )
        raise typer.Exit(code=1)

    console.print(f"Extracting holdings from [bold]{p.name}[/bold] with {client.model}…")
    try:
        result = extract_from_pdf(str(p), client=client, config=config)
    except LocalModelError as e:
        console.print(f"[red]Extraction failed:[/red] {e}")
        raise typer.Exit(code=1)

    if not result.holdings:
        console.print("[yellow]No holdings extracted.[/yellow]")
        raise typer.Exit(code=0)

    table = Table(title=f"Extracted holdings — {p.name}", title_style="bold cyan")
    for col in ("Symbol", "Name", "Class", "Geo", "Quantity", "Market Value", "Ccy"):
        table.add_column(col)
    for h in result.holdings:
        table.add_row(
            h.symbol or "-", h.name, h.asset_class.value, h.geography.value,
            str(h.quantity), str(h.market_value), h.currency,
        )
    console.print(table)
    console.print(f"[dim]{len(result.holdings)} holding(s). Persistence + reconciliation: Week 4.[/dim]")


@app.command()
def ask(
    question: str = typer.Argument(..., help="A question about your portfolio."),
    trace: bool = typer.Option(False, "--trace", help="Show the thought/tool-call/observation trace."),
):
    """Answer a question via the Claude tool-calling loop (concept #1).

    Claude decides which deterministic tool to call (fx_convert / compute_net_worth /
    pdf_extract), reads the JSON result, and composes the answer. No number is computed by the LLM.
    """
    from setu.llm.claude import ClaudeClient, ClaudeError
    from setu.tools.registry import TOOL_SCHEMAS, build_executor

    config = load_config()
    system = (
        "You are Setu, a cross-border wealth assistant. Answer questions about the user's "
        "portfolio. You MUST use the provided tools for any figure — never compute or estimate "
        "numbers yourself. All monetary values are in the base currency unless stated. "
        f"Base currency: {config.base_currency}."
    )

    try:
        client = ClaudeClient(config)
    except ClaudeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    with get_session(config) as session:
        executor = build_executor(session, config)
        result = client.run_tool_loop(question, TOOL_SCHEMAS, executor, system=system)

    if trace:
        console.print("\n[dim]── trace ──[/dim]")
        for step in result.trace:
            if step.kind == "text" and step.content.strip():
                console.print(f"[cyan]thought[/cyan]: {step.content.strip()}")
            elif step.kind == "tool_call":
                console.print(f"[magenta]action[/magenta]: {step.tool_name}({step.content})")
            elif step.kind == "tool_result":
                preview = str(step.content)
                console.print(f"[green]observation[/green] ({step.tool_name}): {preview[:200]}")
        console.print(f"[dim]── {result.rounds} round(s) ──[/dim]\n")

    console.print(result.answer)


if __name__ == "__main__":
    app()
