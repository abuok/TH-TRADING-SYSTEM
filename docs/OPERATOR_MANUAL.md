# Operator Manual: TH Trading System

This manual provides instructions for human-in-the-loop operators to manage,
monitor, and tune the trading system.

## 1. Core Workflow

The system follows a non-executing, data-only pipeline that requires manual
approval for all trades.

1. **Ingestion**: Market data and events are consumed continuously.
2. **Screening**: Technical (PHX) and Fundamental (Bias) models trigger setups.
3. **Risk Audit**: The Risk Engine and Guardrails evaluate setups for safety.
4. **Review Queue**: Approved tickets appear in the Dashboard for human 
   decision.

## 2. Daily Workflow (EAT Times)

- **07:30 - Session Briefing**: Review the `SessionBriefing` on the **Ops** 
  dashboard. Check for upcoming news and current market regime signals.
- **08:00 - Queue Review**: Access the **Queue** dashboard. Verify that 
  expected setups are appearing. Check if any `Guardrails` blocks are active.
- **08:15 - Execution Prep**: For each `Approved` ticket, monitor the 
  **Execution Prep** state. Ensure the system is ready for manual entry.
- **Throughout Session - Trade Management**: Watch the **Management** 
  dashboard for real-time suggestions (Move SL, TP1, etc.).
- **17:00 - End-of-Day Checks**: Review the **Hindsight** dashboard to see 
  realized vs. missed R. Archive the daily session data.

## 3. Handling Blocks

- **Risk Block**: The setup failed the Risk Engine audit (e.g., RR < 1:2 or 
  Drawdown limit hit). Investigation required.
- **Guardrails Block**: A hard safety limit was hit (e.g., maximum daily 
  losses). The system will not process further setups for the session.

---

*Note: This system does NOT trade on your behalf. All broker actions must be 
taken manually after reviewing system output.*
