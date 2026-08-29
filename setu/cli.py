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


@app.command()
def evaluate(
    live_model: bool = typer.Option(
        False,
        "--live-model/--no-live-model",
        help="Also verify exact extraction with the configured local Ollama model.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
):
    """Run the synthetic safety and correctness evaluation without changing the real ledger."""
    import json

    from setu.evaluation import run_evaluation

    report = run_evaluation(load_config(), live_model=live_model)
    if json_output:
        console.print_json(json.dumps(report.as_dict()))
    else:
        table = Table(title="Setu safety and correctness evaluation", show_edge=False)
        table.add_column("Result")
        table.add_column("Metric")
        table.add_column("Observed")
        table.add_column("Target")
        for metric in report.metrics:
            table.add_row(
                "PASS" if metric.passed else "FAIL",
                metric.name,
                metric.value,
                metric.target,
                style="green" if metric.passed else "red",
            )
        console.print(table)
        console.print(
            f"[{'green' if report.passed else 'red'}]"
            f"{'All checks passed' if report.passed else 'Evaluation failed'}[/] "
            f"in {report.elapsed_seconds:.2f}s."
        )
    if not report.passed:
        raise typer.Exit(code=1)


@app.command()
def dashboard(
    port: int = typer.Option(8765, "--port", min=1024, max=65535, help="Local dashboard port."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open the dashboard in a browser."),
):
    """Open Setu's local multi-agent workspace."""
    import threading
    import webbrowser

    import uvicorn

    from setu.dashboard.server import create_app

    config = load_config()
    if config.dashboard_password is None:
        console.print(
            "[red]Dashboard password is not configured.[/red] "
            "Add SETU_DASHBOARD_PASSWORD to the project-local .env file."
        )
        raise typer.Exit(code=1)
    dashboard_app = create_app(config)
    create_all(config)
    url = f"http://127.0.0.1:{port}"
    console.print(f"[green]Setu workspace[/green] is available at [bold]{url}[/bold]")
    console.print("[dim]Runs locally. Press Ctrl+C to stop.[/dim]")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(dashboard_app, host="127.0.0.1", port=port, log_level="warning")


@app.command()
def demo(
    port: int = typer.Option(8765, "--port", min=1024, max=65535),
    reset: bool = typer.Option(False, "--reset", help="Rebuild only the isolated demo ledger."),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
):
    """Launch a synthetic final demo without changing the personal ledger."""
    import threading
    import webbrowser

    import uvicorn

    from setu.agents.orchestrator import Orchestrator
    from setu.dashboard.server import create_app
    from setu.demo import prepare_demo

    runtime = prepare_demo(load_config(), reset=reset)
    if runtime.config.dashboard_password is None:
        console.print(
            "[red]Dashboard password is not configured.[/red] "
            "Add SETU_DASHBOARD_PASSWORD to the project-local .env file."
        )
        raise typer.Exit(code=1)
    dashboard_app = create_app(
        config=runtime.config,
        session_factory=runtime.sessions,
        orchestrator_factory=lambda: Orchestrator(
            runtime.config,
            checkpoint_path=runtime.checkpoint_path,
        ),
    )
    url = f"http://127.0.0.1:{port}"
    console.print("[green]Setu final demo is ready.[/green]")
    console.print(f"Synthetic ledger: [bold]{runtime.config.paths.db_path}[/bold]")
    console.print("Your personal ledger was not changed.")
    console.print(f"Open [bold]{url}[/bold] and sign in with your dashboard password.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(dashboard_app, host="127.0.0.1", port=port, log_level="warning")


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


def _render_trace(trace: list) -> None:
    """Print a run's Thought/Action/Observation trace (the visible ReAct loop)."""
    style = {"thought": "cyan", "action": "magenta", "observation": "green", "ask_user": "yellow"}
    console.print("\n[dim]── trace ──[/dim]")
    for ev in trace:
        kind = ev.get("kind", "?")
        console.print(f"[{style.get(kind, 'white')}]{kind}[/] ({ev.get('node', '')}): {ev.get('content', '')}")
    console.print("[dim]───────────[/dim]\n")


@app.command()
def ingest(
    path: str = typer.Argument(..., help="Path to a PDF statement."),
    thread: str = typer.Option(None, "--thread", help="Thread id (checkpoint key). Defaults to the file name."),
    trace: bool = typer.Option(True, "--trace/--no-trace", help="Show the Thought/Action/Observation trace."),
):
    """Ingest a statement through the LangGraph pipeline (Week 3).

    Orchestrator → ingest (parse + local extraction) → reconcile (sum vs stated total) →
    persist / ask_user. The run is checkpointed under `--thread`; on a reconciliation mismatch it
    pauses for a human — answer with `setu resume <thread> <accept|reject>`.
    """
    from setu.agents.orchestrator import Orchestrator
    from setu.llm.local import LocalClient
    from setu.tools.pdf_extract import OcrError

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

    thread_id = thread or p.stem
    console.print(f"Ingesting [bold]{p.name}[/bold] (thread [dim]{thread_id}[/dim]) with {client.model}…")
    try:
        with Orchestrator(config) as orch:
            outcome = orch.ingest(str(p), thread_id)
    except OcrError as exc:
        console.print(f"[red]OCR failed:[/red] {exc}")
        raise typer.Exit(code=1)

    if trace:
        _render_trace(outcome.trace)

    if outcome.status == "interrupted":
        console.print(f"[yellow]⏸ Paused for review:[/yellow] {outcome.question}")
        console.print(f"Resume with: [bold]setu resume {thread_id} accept[/bold]  (or [bold]reject[/bold])")
        raise typer.Exit(code=0)

    if outcome.state.get("persisted_skipped"):
        console.print("[yellow]Already ingested[/yellow] — skipped (idempotent).")
    else:
        if outcome.persisted_policies:
            console.print(
                f"[green]✓ Ingested[/green] {outcome.persisted_policies} policy value(s) and "
                f"{outcome.persisted_obligations} premium obligation(s); "
                f"validation: [bold]{outcome.reconcile_status}[/bold]."
            )
        elif outcome.persisted_balances:
            console.print(
                f"[green]✓ Ingested[/green] {outcome.persisted_balances} bank balance(s); "
                f"reconciliation: [bold]{outcome.reconcile_status}[/bold]."
            )
        else:
            console.print(
                f"[green]✓ Ingested[/green] {outcome.persisted_holdings} holding(s); "
                f"reconciliation: [bold]{outcome.reconcile_status}[/bold]."
            )


@app.command()
def resume(
    thread: str = typer.Argument(..., help="Thread id of the paused run."),
    decision: str = typer.Argument(..., help="accept | reject"),
    trace: bool = typer.Option(True, "--trace/--no-trace"),
):
    """Resume a run that paused at a human-in-the-loop reconciliation review."""
    from setu.agents.orchestrator import Orchestrator

    config = load_config()
    with Orchestrator(config) as orch:
        outcome = orch.resume(thread, decision.strip().lower())

    if trace:
        _render_trace(outcome.trace)

    if (
        outcome.state.get("persisted_holdings")
        or outcome.state.get("persisted_balances")
        or outcome.state.get("persisted_policies")
    ):
        console.print(
            f"[green]✓ Resumed[/green] — wrote {outcome.persisted_holdings} holding(s), "
            f"{outcome.persisted_balances} balance(s), "
            f"{outcome.persisted_policies} policy value(s), and "
            f"{outcome.persisted_obligations} obligation(s)."
        )
    else:
        console.print("[yellow]Resumed — nothing persisted[/yellow] (rejected or already ingested).")


@app.command()
def ask(
    question: str = typer.Argument(..., help="A question about your portfolio."),
    trace: bool = typer.Option(False, "--trace", help="Show the thought/tool-call/observation trace."),
):
    """Answer a question via the Claude tool-calling loop (concept #1).

    Claude decides which deterministic tool to call (FX, net worth, or portfolio analysis), reads
    the sanitized JSON result, and composes the answer. Raw document text is never exposed to the
    cloud tool loop, and no number is computed by the LLM.
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
