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
def seed(fresh: bool = typer.Option(True, "--fresh/--no-fresh", help="Recreate tables first.")):
    """Generate the synthetic US+India portfolio and ground-truth fixture."""
    from setu.synthetic.generate import seed_portfolio, write_ground_truth

    config = load_config()
    if fresh:
        drop_all(config)
    create_all(config)
    with get_session(config) as session:
        seed_portfolio(session, config)
    gt = write_ground_truth(config)
    console.print("[green]Seeded synthetic portfolio.[/green]")
    console.print(f"Ground truth written; net worth = {_money(Decimal(gt['total']), config.base_currency)}")


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
def ingest(path: str = typer.Argument(..., help="Statement file or glob.")):
    """[stub — Week 2+] Parse and reconcile real statements into the ledger."""
    console.print("[yellow]ingest[/yellow] arrives in Week 2+ (parsing) / Week 4 (reconciliation).")
    console.print(f"Would ingest: {path}")


@app.command()
def ask(question: str = typer.Argument(..., help="A question about your portfolio.")):
    """[stub — Week 7] Q&A over the consolidated portfolio."""
    console.print("[yellow]ask[/yellow] arrives in Week 7 (InsightsAgent).")
    console.print(f"Would answer: {question!r}")


if __name__ == "__main__":
    app()
