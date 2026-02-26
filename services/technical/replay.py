import typer
import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from shared.adapters.price_feed import CSVPriceFeedAdapter
from shared.logic.sessions import TradingSessions
from shared.logic.phx_detector import PHXDetector, PHXStage
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()

@app.command()
def scan(csv_path: str = "data/sample_ohlcv.csv", days: int = 30, timeframe: str = "1H"):
    """
    Run a simulated technical scan on historical data with session levels and PHX detection.
    """
    if not os.path.exists(csv_path):
        console.print(f"[red]Error: File {csv_path} not found.[/red]")
        return

    console.print(f"[blue]Starting technical scan on {csv_path} for the last {days} days...[/blue]")
    
    adapter = CSVPriceFeedAdapter(csv_path)
    candles = adapter.get_last_n_days(days=days, timeframe=timeframe)
    
    if not candles:
        console.print("[yellow]No data found for the specified period.[/yellow]")
        return

    console.print(f"[green]Loaded {len(candles)} candles ({timeframe}).[/green]")
    
    # PHX Detection
    detector = PHXDetector(asset_pair="UNKNOWN")
    best_score = 0
    best_stage = PHXStage.IDLE
    best_reasons = []

    for candle in candles:
        detector.update(candle)
        if detector.get_score() > best_score:
            best_score = detector.get_score()
            best_stage = detector.stage
            best_reasons = list(detector.reason_codes)

    # Compute session levels for the most recent day in the set
    session_levels = TradingSessions.compute_all_levels(candles)
    
    # Simple "mock" scan logic
    bullish_count = sum(1 for c in candles if c.close > c.open)
    bearish_count = len(candles) - bullish_count
    
    table = Table(title=f"Scan Results (Last {days} days)")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    
    table.add_row("Total Candles", str(len(candles)))
    table.add_row("Bullish Candles", str(bullish_count))
    table.add_row("Bearish Candles", str(bearish_count))
    table.add_row("Avg Close Price", f"{sum(c.close for c in candles)/len(candles):.2f}")
    
    # Add session levels to the table
    for level_name, value in session_levels.items():
        table.add_row(level_name.replace("_", " ").title(), f"{value:.2f}")

    # Add PHX Result
    table.add_section()
    table.add_row("PHX Setup Score", str(best_score), style="bold yellow")
    table.add_row("PHX Current Stage", best_stage.name)
    if best_reasons:
        table.add_row("Latest Reason", best_reasons[-1], style="italic")

    console.print(table)
    console.print("\n[bold green]Scan completed successfully![/bold green]")

if __name__ == "__main__":
    app()
