# ruff: noqa: E402  # delayed imports/path setup required in this module
import typer
import os
import sys

# Ensure the root directory is in the sys.path for importing shared
sys.path.append(os.getcwd())

import shared.database.session as db_session
from shared.database.models import Packet, Run, KillSwitch
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command()
def list_packets(limit: int = 10):
    """List the latest packets from the database."""
    db = db_session.SessionLocal()
    try:
        packets = db.query(Packet).order_by(Packet.created_at.desc()).limit(limit).all()

        if not packets:
            console.print("[yellow]No packets found in database.[/yellow]")
            return

        table = Table(title=f"Latest {limit} Packets")
        table.add_column("ID", style="cyan")
        table.add_column("Run ID", style="magenta")
        table.add_column("Type", style="green")
        table.add_column("Version", style="blue")
        table.add_column("Created At", style="white")

        for p in packets:
            # Note: run.run_id is the string identifier, run_id is the foreign key
            run_display = p.run.run_id if p.run else str(p.run_id)
            table.add_row(
                str(p.id),
                run_display,
                p.packet_type,
                p.schema_version,
                p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print(table)
    finally:
        db.close()


@app.command()
def list_runs(limit: int = 5):
    """List the latest execution runs."""
    db = db_session.SessionLocal()
    try:
        runs = db.query(Run).order_by(Run.started_at.desc()).limit(limit).all()

        table = Table(title=f"Latest {limit} Runs")
        table.add_column("Internal ID")
        table.add_column("Run ID")
        table.add_column("Status")
        table.add_column("Started At")

        for r in runs:
            table.add_row(
                str(r.id),
                r.run_id,
                r.status,
                r.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print(table)
    finally:
        db.close()


@app.command()
def set_kill_switch(switch_type: str, target: str = None):
    """Set a kill switch. Types: HALT_ALL, HALT_PAIR, HALT_SERVICE, HALT_EXECUTION"""
    db = db_session.SessionLocal()
    try:
        ks = KillSwitch(switch_type=switch_type, target=target, is_active=1)
        db.add(ks)
        db.commit()
        console.print(f"[red]Kill switch {switch_type} {target or ''} activated.[/red]")
    finally:
        db.close()


@app.command()
def unset_kill_switch(switch_id: int):
    """Deactivate a kill switch by ID."""
    db = db_session.SessionLocal()
    try:
        ks = db.query(KillSwitch).filter(KillSwitch.id == switch_id).first()
        if ks:
            ks.is_active = 0
            db.commit()
            console.print(
                f"[green]Kill switch {ks.switch_type} {ks.target or ''} deactivated.[/green]"
            )
        else:
            console.print(f"[yellow]Kill switch ID {switch_id} not found.[/yellow]")
    finally:
        db.close()


@app.command()
def list_kill_switches():
    """List all active and inactive kill switches."""
    db = db_session.SessionLocal()
    try:
        kss = db.query(KillSwitch).all()
        table = Table(title="Kill Switches")
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Target")
        table.add_column("Status")
        table.add_column("Created At")

        for ks in kss:
            status = "[red]ACTIVE[/red]" if ks.is_active else "[green]INACTIVE[/green]"
            table.add_row(
                str(ks.id),
                ks.switch_type,
                ks.target or "-",
                status,
                ks.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print(table)
    finally:
        db.close()


import json
from datetime import datetime
import yaml


def save_json(result):
    from services.research.reporting import save_research_run

    return save_research_run(result)


def generate_html_report(result):
    from jinja2 import Environment, FileSystemLoader
    import os

    env = Environment(
        loader=FileSystemLoader(os.path.join("services", "dashboard", "templates"))
    )
    template = env.get_template("research_report_template.html")
    html_content = template.render(run=result, now=datetime.now())
    os.makedirs(os.path.join("artifacts", "research"), exist_ok=True)
    filepath = os.path.join("artifacts", "research", f"{result.run_id}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


# Add Research sub-app
research_app = typer.Typer(help="Research algorithms and generation")
pilot_app = typer.Typer(help="Pilot Protocol & Graduation Gate")
infra_app = typer.Typer(help="Infrastructure & Integration status")

app.add_typer(research_app, name="research")
app.add_typer(pilot_app, name="pilot")
app.add_typer(infra_app, name="infra")


@research_app.command("run")
def research_run(
    pair: str,
    date_from: str,
    date_to: str,
    csv_path: str,
    timeframe: str = "15m",
    variants_file: str = typer.Option(
        None, "--variants", help="YAML file with CounterfactualConfigs"
    ),
):
    """Run a historical replay and generate reports."""
    from shared.types.research import CounterfactualConfig
    from services.research.simulator import run_replay

    try:
        dt_from = datetime.fromisoformat(date_from)
        dt_to = datetime.fromisoformat(date_to)
    except ValueError:
        console.print("[red]Invalid date format. Use YYYY-MM-DD or ISO 8601[/red]")
        raise typer.Exit(1)

    variants = {"baseline": CounterfactualConfig()}
    if variants_file and os.path.exists(variants_file):
        with open(variants_file, "r") as f:
            raw = yaml.safe_load(f)
            for k, v in raw.items():
                variants[k] = CounterfactualConfig(**v)

    with console.status(
        f"[bold green]Running replay on {pair} from {dt_from.date()} to {dt_to.date()}...[/]"
    ):
        try:
            result = run_replay(csv_path, pair, timeframe, dt_from, dt_to, variants)
        except Exception as e:
            console.print(f"[red]Replay failed: {e}[/red]")
            raise typer.Exit(1)

    json_path = save_json(result)
    html_path = generate_html_report(result)

    console.print(f"\n[green]Success![/] Saved {result.run_id} to {json_path}")
    console.print(f"HTML Report: {html_path}")


@research_app.command("calibrate")
def research_calibrate(
    run_id: str,
    baseline: str = typer.Option(
        "baseline", "--baseline", "-b", help="Name of the variant to use as baseline"
    ),
):
    """Generate a Policy Calibration pack from a historical replay run."""
    try:
        from services.research.calibration import generate_calibration_report
        from services.research.reporting import (
            compile_calibration_html,
            load_research_run,
            save_calibration_report,
        )

        run_res = load_research_run(run_id)

        with console.status(f"[bold green]Generating calibration for {run_id}...[/]"):
            report = generate_calibration_report([run_res], baseline_name=baseline)
            json_path = save_calibration_report(report)
            html_path = compile_calibration_html(report)

        console.print(f"\n[green]Calibration Pack Generated for {report.pair}![/]")
        num_recs = len(report.recommendations)
        console.print(f"Found [cyan]{num_recs}[/] statistical recommendations.")
        console.print(f"JSON Output: {json_path}")
        console.print(f"HTML Output: {html_path}")

    except FileNotFoundError:
        console.print(
            f"[red]Could not find run_id '{run_id}'. Run 'python infra/cli.py research list' to see available runs.[/red]"
        )
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Calibration failed: {e}[/red]")
        raise typer.Exit(1)


@research_app.command("list")
def research_list():
    """List historical research runs from the artifacts directory."""
    if not os.path.exists("artifacts/research"):
        console.print(
            "[yellow]No research runs found (artifacts/research missing).[/yellow]"
        )
        return

    files = [f for f in os.listdir("artifacts/research") if f.endswith(".json")]
    if not files:
        console.print("[yellow]No research runs found.[/yellow]")
        return

    table = Table(title="Recent Research Runs")
    table.add_column("Run ID")
    table.add_column("Pair")
    table.add_column("Dates")
    table.add_column("Variants")

    for fname in sorted(files, reverse=True)[:10]:
        with open(os.path.join("artifacts/research", fname), "r") as f:
            data = json.load(f)
            run_id = data.get("run_id", "Unknown")
            pair = data.get("pair", "Unknown")
            dates = (
                f"{data.get('start_date', '')[:10]} -> {data.get('end_date', '')[:10]}"
            )
            v_count = len(data.get("variants", {}))
            table.add_row(run_id, pair, dates, str(v_count))

    console.print(table)


@research_app.command("show")
def research_show(run_id: str):
    """Show high-level metrics for a specific run ID."""
    filepath = f"artifacts/research/{run_id}.json"
    if not os.path.exists(filepath):
        console.print(f"[red]Run {run_id} not found at {filepath}[/red]")
        raise typer.Exit(1)

    with open(filepath, "r") as f:
        data = json.load(f)

    console.print(f"\n[bold cyan]Run Summary: {run_id}[/bold cyan]")
    console.print(f"Pair: {data.get('pair')}")
    console.print(f"Dates: {data.get('start_date')} to {data.get('end_date')}\n")

    for v_name, v_data in data.get("variants", {}).items():
        m = v_data.get("metrics", {})
        console.print(f"[bold]{v_name.upper()}[/bold]")
        console.print(
            f"  Trades Executed / Total:  {m.get('executed_trades')} / {m.get('total_trades')} ({m.get('blocked_trades')} blocked)"
        )
        console.print(
            f"  Win Rate:                 [green]{m.get('win_rate_pct')}%[/green]"
        )
        console.print(f"  Expectancy (R):           {m.get('expectancy_r')}R")
        console.print(
            f"  Max Drawdown (R):         [red]-{m.get('max_drawdown_r')}R[/red]"
        )
        console.print(f"  Total R:                  [bold]{m.get('total_r')}R[/bold]\n")


@research_app.command("validate-proposals")
def validate_proposals(
    pair: str,
    date_from: str,
    date_to: str,
    csv_path: str,
    proposal_id: str,
    timeframe: str = "15m",
):
    """Validate a tuning proposal by running research simulations over a historical window."""
    from shared.types.research import CounterfactualConfig
    from services.research.simulator import run_replay

    try:
        dt_from = datetime.fromisoformat(date_from)
        dt_to = datetime.fromisoformat(date_to)
    except ValueError:
        console.print("[red]Invalid date format. Use YYYY-MM-DD or ISO 8601[/red]")
        raise typer.Exit(1)

    db = db_session.SessionLocal()
    try:
        from shared.database.models import TuningProposalLog

        # 1. Fetch the Proposal
        log = (
            db.query(TuningProposalLog)
            .filter(TuningProposalLog.data["proposals"].contains([{"id": proposal_id}]))
            .first()
        )
        if not log:
            console.print(f"[red]Proposal '{proposal_id}' not found.[/red]")
            return

        proposals = log.data.get("proposals", [])
        prop = next((p for p in proposals if p["id"] == proposal_id), None)
        if not prop:
            console.print(
                f"[red]Proposal '{proposal_id}' not found in log {log.report_id}.[/red]"
            )
            return

        # 2. Extract proposed change to build counterfactual
        # In a real system, you'd map standard proposals perfectly to CounterfactualConfig args
        # Here we mock standard mappings for Guardrails/Queue/Management
        variant = CounterfactualConfig()
        if "guardrails" in prop["target"]:
            # e.g., soften discipline score
            console.print(f"Applying Guardrails patch for proposal: {proposal_id}")
            variant = CounterfactualConfig(ignore_guardrails_blocks=True)

        variants = {
            "baseline": CounterfactualConfig(),
            f"proposed_{proposal_id}": variant,
        }
    finally:
        db.close()

    with console.status(
        f"[bold green]Simulating Baseline vs {proposal_id} on {pair} from {dt_from.date()} to {dt_to.date()}...[/]"
    ):
        try:
            result = run_replay(csv_path, pair, timeframe, dt_from, dt_to, variants)
        except Exception as e:
            console.print(f"[red]Replay failed: {e}[/red]")
            raise typer.Exit(1)

    _ = save_json(result)

    console.print(f"\n[bold cyan]Validation Complete for {proposal_id}[/bold cyan]")

    base_m = result.variants["baseline"].metrics
    prop_m = result.variants[f"proposed_{proposal_id}"].metrics

    console.print("\n[bold]Metrics Comparison:[/bold]")
    table = Table()
    table.add_column("Metric")
    table.add_column("Baseline")
    table.add_column("Proposed")
    table.add_column("Delta")

    def add_metric(name, m_key):
        b_val = base_m.get(m_key, 0)
        p_val = prop_m.get(m_key, 0)
        if isinstance(b_val, float):
            delta = f"{(p_val - b_val):+.2f}"
            table.add_row(name, f"{b_val:.2f}", f"{p_val:.2f}", delta)
        elif isinstance(b_val, int):
            delta = f"{(p_val - b_val):+d}"
            table.add_row(name, str(b_val), str(p_val), delta)

    add_metric("Total R", "total_r")
    add_metric("Win Rate (%)", "win_rate_pct")
    add_metric("Max Drawdown (R)", "max_drawdown_r")
    add_metric("Total Executed", "executed_trades")

    console.print(table)

    if prop_m.get("total_r", 0) > base_m.get("total_r", 0):
        console.print(
            f"[bold green]Proposal '{proposal_id}' IMPROVES performance on historical data![/]"
        )
    else:
        console.print(
            f"[bold yellow]Proposal '{proposal_id}' DOES NOT improve performance on historical data.[/]"
        )


# --- PILOT RUN PROTOCOL COMMANDS ---


@pilot_app.command("build-scorecard")
def build_scorecard(
    from_date: str = typer.Option(..., "--from", help="Start date (YYYY-MM-DD)"),
    to_date: str = typer.Option(..., "--to", help="End date (YYYY-MM-DD)"),
):
    """
    Build a Pilot Scorecard for a specified rolling window, computing graduation gates.
    """
    from datetime import datetime
    from shared.database.connection import get_db
    from services.research.pilot import build_pilot_scorecard

    start_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(to_date, "%Y-%m-%d").date()

    db = next(get_db())
    print(f"Building Pilot Scorecard evaluating {start_dt} to {end_dt}...")

    scorecard = build_pilot_scorecard(db, start_dt, end_dt)

    print(f"\n--- SCORECARD {scorecard.scorecard_id} ---")
    print(f"Overview Pass/Fail: {scorecard.pass_fail_summary}")
    print("\nNext Week Plan:")
    for plan in scorecard.next_week_plan:
        print(f" - {plan}")

    print("\nScorecard and dependencies built and logged directly to artifacts/pilot/")


@pilot_app.command("latest")
def get_latest_scorecard():
    """
    Fetch the latest pilot scorecard aggregates from the database.
    """
    from shared.database.connection import get_db
    from shared.database.models import PilotScorecardLog

    db = next(get_db())
    latest = (
        db.query(PilotScorecardLog)
        .order_by(PilotScorecardLog.created_at.desc())
        .first()
    )

    if not latest:
        print("No pilot scorecards found.")
        return

    print(f"Scorecard: {latest.scorecard_id}")
    print(f"Dates Evaluated: {latest.date_range}")
    print(f"PASS/FAIL: {latest.pass_fail}")


# --- INFRASTRUCTURE COMMANDS ---


@infra_app.command("status")
def integrations_status():
    """
    Print status of all external integrations and environment variables.
    """
    from shared.providers.calendar import get_calendar_provider
    from shared.providers.proxy import get_proxy_provider
    from shared.providers.price_quote import get_price_quote_provider
    from shared.providers.symbol_spec import get_symbol_spec_provider
    import redis

    table = Table(title="Integration Status")
    table.add_column("Provider Type", style="cyan")
    table.add_column("Active Implementation", style="magenta")
    table.add_column("Env Var", style="green")
    table.add_column("Status", style="white")

    def check_provider(name, env_var, factory_func, required_vars=[]):
        try:
            impl = factory_func()
            impl_name = type(impl).__name__

            # Check for missing credentials for real providers
            missing_creds = [v for v in required_vars if not os.getenv(v)]

            if "Mock" in impl_name:
                status = "[yellow]MOCK[/yellow]"
            elif missing_creds:
                status = f"[red]MISSING: {', '.join(missing_creds)}[/red]"
            else:
                status = "[green]OK[/green]"

            table.add_row(name, impl_name, os.getenv(env_var, "unset"), status)
        except Exception as e:
            table.add_row(name, "ERROR", os.getenv(env_var, "unset"), f"[red]{e}[/red]")

    check_provider(
        "Calendar",
        "CALENDAR_PROVIDER",
        get_calendar_provider,
        ["FOREX_FACTORY_API_KEY"],
    )
    check_provider(
        "Proxy", "PROXY_PROVIDER", get_proxy_provider, ["TWELVE_DATA_API_KEY"]
    )
    check_provider("Price Quote", "PRICE_PROVIDER", get_price_quote_provider)
    check_provider("Symbol Spec", "SPEC_PROVIDER", get_symbol_spec_provider)

    console.print(table)

    # Redis & Subscriptions
    console.print("\n[bold]Subsystem Wiring (Redis):[/bold]")
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            r = redis.Redis.from_url(redis_url)
            r.ping()
            console.print(f" - Redis: [green]CONNECTED[/green] ({redis_url})")

            # Check consumer groups for Risk Service
            streams = ["market_context", "technical_setups", "risk_approvals"]
            for s in streams:
                try:
                    groups = r.xinfo_groups(s)
                    group_names = [g["name"] for g in groups]
                    status = (
                        f"[green]OK[/green] ({', '.join(group_names)})"
                        if groups
                        else "[yellow]NO GROUPS[/yellow]"
                    )
                except redis.exceptions.ResponseError:
                    status = "[red]STREAM MISSING[/red]"
                console.print(f"   - Stream '{s}': {status}")

        except Exception as e:
            console.print(f" - Redis: [red]FAILED[/red] ({e})")
    else:
        console.print(" - Redis: [red]REDIS_URL NOT SET[/red]")

    # Required secrets
    console.print("\n[bold]Core Secrets Check:[/bold]")
    secrets = ["DATABASE_URL", "REDIS_URL", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
    for s in secrets:
        val = os.getenv(s)
        status = "[green]SET[/green]" if val else "[red]MISSING[/red]"
        console.print(f" - {s:20}: {status}")


if __name__ == "__main__":
    app()
