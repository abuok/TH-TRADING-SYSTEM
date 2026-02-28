# Operator Manual (v1.0.0)

This manual provides instructions for the daily operation and management of the Trading System.

## Daily Workflow (EAT Times)

- **07:30 - Session Briefing**: Review the `SessionBriefing` on the **Ops** dashboard. Check for upcoming high-impact news and current market regime signals.
- **08:00 - Queue Review**: Access the **Queue** dashboard. Verify that expected setups for the session are appearing. Check if any `Guardrails` blocks are active.
- **08:15 - Execution Prep**: For each `Approved` ticket, monitor the **Execution Prep** state. Ensure the system is ready to hit the broker entry prices.
- **Throughout Session - Trade Management**: Watch the **Management** dashboard for real-time suggestions (Move SL to BE, TP1, etc.).
- **17:00 - End-of-Day Checks**: Review the **Hindsight** dashboard to see realized vs. missed R. Archive the daily session data.
- **Weekly (Friday Close)**: Generate and review the **Tuning** proposal report.

## Dashboard Overview

- **Ops**: High-level system health, session briefs, and active alerts.
- **Tickets**: Full history of generated order tickets and their current lifecycle status.
- **Queue**: Active tickets waiting for execution or undergoing guardrail checks.
- **Hindsight**: Analysis of what the system *should* have done vs. what it actually did.
- **Calibration**: Tools for adjusting risk-reward and entry/exit parameters based on backtests.
- **Tuning**: Weekly parameter suggestions grounded in historical outcome data.
- **Pilot**: Rolling 10-session scorecard for system graduation status.
- **Policies**: Active regime-based logic maps and signal scoring weights.
- **Live Data**: Real-time quote bridge status and provider latency checks.
- **Trades**: Live positions and fills captured directly from the broker (MT5).
- **Management**: Rule-based trade adjustment suggestions.

## How to Approve/Skip/Override

- **Approve**: Only approve tickets that align with the current session's regime policy.
- **Skip**: Use the `SKIP` button if a ticket is generated during high-impact news (within +/- 30 mins) or if spread is > 3x average.
- **Override**: Manual overrides in Execution Prep should be rare and documented with a reason (e.g., "Broker connection unstable"). **Never override SL/TP to increase risk.**

## Interpreting Key Metrics

- **Expectancy (R)**: The average return per trade. Graduation requires > 0.05R.
- **Max Drawdown (R)**: The deepest peak-to-valley loss. Stop trading if it exceeds -5.0R.
- **Missed R**: Potential profit from skipped tickets that hit TP. High missed R suggests overly restrictive policies.
- **Override Rate**: The % of manual interventions. High rates (> 10%) indicate the automation rules need tuning.

## Safe Tuning Procedures

1. Review the **Tuning Proposal** on the dashboard.
2. Run `python -m infra.cli tuning validate-proposals --id <ID>` to see counterfactual simulation results.
3. If results show improvement, apply the YAML patch provided in the dashboard.
4. **Rollback**: To revert, restore the previous `config/*.yaml` file from the `backups/` directory or your version control system.
