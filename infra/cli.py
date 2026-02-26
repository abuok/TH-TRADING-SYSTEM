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
                p.created_at.strftime("%Y-%m-%d %H:%M:%S")
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
            table.add_row(str(r.id), r.run_id, r.status, r.started_at.strftime("%Y-%m-%d %H:%M:%S"))
        
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
            console.print(f"[green]Kill switch {ks.switch_type} {ks.target or ''} deactivated.[/green]")
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
            table.add_row(str(ks.id), ks.switch_type, ks.target or "-", status, ks.created_at.strftime("%Y-%m-%d %H:%M:%S"))
        
        console.print(table)
    finally:
        db.close()

if __name__ == "__main__":
    app()
