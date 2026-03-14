"""
services/research/research_cli.py
CLI for running research simulations and comparing policies.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

# Ensure root is in path
sys.path.append(os.getcwd())

from services.research.reporting import generate_research_report
from services.research.simulator import run_replay
from shared.types.research import CounterfactualConfig


def compare_router(csv_path: str, pair: str, start_days: int):
    """
    Compares Baseline policy vs Regime-Adaptive Policy Router.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=start_days)

    variants = {
        "Fixed_Baseline": CounterfactualConfig(use_router=False),
        "Adaptive_Router": CounterfactualConfig(use_router=True),
    }

    print(f"--- Running Comparative Performance Test: {pair} ---")
    print(f"Period: {start_date.date()} to {end_date.date()} ({start_days} days)")

    result = run_replay(
        csv_path=csv_path,
        pair=pair,
        timeframe="15m",
        start_date=start_date,
        end_date=end_date,
        variants=variants,
    )

    # Generate artifacts
    report_path = generate_research_report(result)

    # Summary Table
    print("\n| Metric | Fixed Baseline | Adaptive Router |")
    print("|--------|----------------|-----------------|")
    b = result.variants["Fixed_Baseline"].metrics
    a = result.variants["Adaptive_Router"].metrics

    print(f"| Executed Trades | {b.executed_trades} | {a.executed_trades} |")
    print(f"| Blocked Trades  | {b.blocked_trades} | {a.blocked_trades} |")
    print(f"| Win Rate        | {b.win_rate_pct}% | {a.win_rate_pct}% |")
    print(f"| Total R         | {b.total_r}R | {a.total_r}R |")
    print(f"| Profit Factor   | {b.profit_factor} | {a.profit_factor} |")
    print(f"| Expectancy      | {b.expectancy_r}R | {a.expectancy_r}R |")

    print(f"\nReport generated: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PHX Research CLI")
    subparsers = parser.add_subparsers(dest="command")

    # compare-router command
    comp_parser = subparsers.add_parser("compare-router")
    comp_parser.add_argument(
        "--csv", type=str, required=True, help="Path to historical CSV"
    )
    comp_parser.add_argument("--pair", type=str, default="XAUUSD", help="Asset pair")
    comp_parser.add_argument(
        "--days", type=int, default=30, help="Number of days to look back"
    )

    args = parser.parse_args()

    if args.command == "compare-router":
        compare_router(args.csv, args.pair, args.days)
    else:
        parser.print_help()
