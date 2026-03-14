# Friend Walkthrough: The TH Trading System

## A calm, complete guide for someone who has never traded before

> **Tone**: Think of this system as a luxury control room for a financial analyst. Everything is tracked, everything is logged, nothing happens by accident. You are the pilot; the system is the cockpit.

---

## TABLE OF CONTENTS

- [Section A — What This System Is](#section-a--what-this-system-is)
- [Section B — The Moving Parts](#section-b--the-moving-parts)
- [Section C — How to Run It](#section-c--how-to-run-it)
- [Section D — How to Use It (Daily Operator Tutorial)](#section-d--how-to-use-it-daily-operator-tutorial)
- [Section E — The Weekly Improvement Loop](#section-e--the-weekly-improvement-loop)
- [Section F — Glossary](#section-f--glossary)
- [Section G — Quickstart Cheat Sheet](#section-g--quickstart-cheat-sheet)
- [Reality Check](#reality-check)

---

## SECTION A — What This System Is

### The Problem It Solves

Imagine you follow a set of trading rules. You have a strategy. You wait for
specific conditions — a particular pattern, a price retracement — and you only
trade during certain hours when the market is most reliable. You know your
rules cold.

But then:

- You miss a good trade because you were at lunch.
- You skip one because news was about to be released and it felt risky.
- You take a trade that technically met the criteria, but your journal entry
  was vague.
- Three months later, you have no idea which rules were working and which
  weren't.

**This is the problem.** Human traders are inconsistent, forgetful, and
emotional. They often trade well on one session and badly on the next, and they
can't reliably improve because their records are incomplete.

**This system solves all of that.** It turns trading into a structured,
auditable *desk process* — like how a hospital uses checklists before surgery,
or how a pilot runs a pre-flight checklist before takeoff.

### What It Is NOT

- ❌ It is **not** an "auto-profit bot." It does not find magic trades and make
  you rich in your sleep.
- ❌ It is **not autonomous.** It **never** places a trade on your behalf.
- ❌ It is **not a shortcut.** It makes disciplined trading *possible*, not
  *guaranteed*.

### The Big Idea: Desk Workflow + Governance + Human Approval

The system acts like a disciplined analyst who works for you. It:

1. **Watches the markets** and identifies potential trade setups according to
   strict rules.
2. **Checks those setups** against safety rules (news events, risk limits,
   session hours).
3. **Generates a "ticket"** — a written proposal — for each valid setup.
4. **Waits for YOU** to review and approve (or reject) each ticket.
5. **Records everything** — what was approved, what was skipped, what
   happened.
6. **Learns from history** — surfacing which rules are working and proposing
   improvements.

You, the operator, are in control at all times.

---

### Key Concepts Explained Simply

#### Markets & Pairs

The system trades **forex (foreign exchange)**. Forex is the buying and selling
of currencies. For example, GBPJPY means: "How many Japanese Yen does it cost
to buy one British Pound?" The price moves constantly.

XAUUSD is Gold priced in US Dollars. These "pairs" are what the system watches.

#### Sessions (Asia / London / New York)

The forex market is global and open 24 hours, but activity is concentrated in
three *sessions* — time windows when specific banks and institutions are most
active. In East Africa Time (EAT):

- **London session**: ~11:00–20:00 EAT — most liquid, most reliable.
- **New York session**: ~16:00–01:00 EAT — overlaps with London for peak hours.
- **Asia session**: overnight — generally quieter. The system avoids this by
  default.

The system only triggers setups during the configured sessions.

#### Spread

When you buy a currency pair, there's a tiny gap between the buy price and the
sell price. This is the **spread** — the broker's cut. If the spread is
unusually wide (e.g., during news events), it's a bad time to trade because you
start every trade at a bigger loss. The system checks and warns about wide
spreads.

#### Risk Limits

The system enforces rules like:

- "Don't trade if you've lost 3 times in a row." (Consecutive loss limit)
- "Don't trade if you've lost more than 2% of your account today." (Daily
  drawdown limit)
- "This trade must offer at least 2:1 reward vs. risk." (Minimum RR ratio)

These rules are not negotiable — the system blocks you automatically.

#### What a "Setup" Means

A "setup" is a specific market condition where all the technical stars align
according to the strategy: the market has swept liquidity, displaced in a
direction, broken structure, and is now pulling back to a specific zone. It's
the trading equivalent of "the conditions are right — this is the moment to
consider entering."

#### PHX Stages (High-Level)

The system uses a strategy called **PHX** (Price Hunting eXecution). It tracks
market stages in sequence:

1. **BIAS** — The overall direction (up or down) is identified.
2. **SWEEP** — The market clears out stop orders (a classic institutional
   move).
3. **DISPLACE** — Strong, decisive price movement confirms the direction.
4. **CHOCH/BOS** — Change of Character / Break of Structure — structural
   confirmation.
5. **RETEST** — Price comes back to test the breakout zone.
6. **TRIGGER** — The exact entry condition is met.

Only when a setup reaches the required stage (typically RETEST or TRIGGER) is a
ticket generated.

#### No-Trade Windows (News Events)

Every week, economic news events are scheduled — central bank announcements,
employment data, inflation reports. When these drop, markets move violently and
unpredictably. Trading during these windows is dangerous.

The system fetches a calendar of upcoming high-impact events and enforces a
buffer window (default ±30 minutes) around them. During this window, **no new
tickets are approved** and the system raises a visible warning.

#### Fail Closed

"Fail closed" means: **if the system can't verify something is safe, it blocks
rather than permits.**

Examples:

- If the system can't get a live price quote: **block**. Don't guess.
- If the market context data is older than 2 hours: **block**. It might be
  stale.
- If the production environment is missing API keys for a required provider:
  **raise an error**, not a silent fallback.

This design philosophy means a broken connection causes a conservative halt,
not a reckless trade.

---

## SECTION B — The Moving Parts

### Data Flow Diagram

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                        MARKET DATA (EXTERNAL)                         │
   │    Calendar Events · Macro Proxies (DXY, US10Y) · MT5 Price Bridge    │
   └─────────────────────────────┬──────────────────────────────────────────┘
                                 │
                                 ▼
   ┌──────────────┐    ┌──────────────────┐    ┌────────────────────────────┐
   │  INGESTION   │───▶│  FUNDAMENTALS    │───▶│  TECHNICAL SCANNER (PHX)   │
   │  Service     │    │  Engine          │    │  Stage Tracker + Scorer    │
   └──────────────┘    └──────────────────┘    └───────────────┬────────────┘
                                                               │
                                          ┌────────────────────▼────────────┐
                                          │  GUARDRAILS ENGINE               │
                                          │  (7 safety rules checked)        │
                                          └────────────────────┬─────────────┘
                                                               │
                                          ┌────────────────────▼────────────┐
                                          │  RISK ENGINE                     │
                                          │  (RR, drawdown, event window)    │
                                          └────────────────────┬─────────────┘
                                                               │
                                          ┌────────────────────▼────────────┐
                                          │  TICKET GENERATOR                │
                                          │  (human-reviewable data packet)  │
                                          └────────────────────┬─────────────┘
                                                               │
                     ┌─────────────────────────────────────────▼────────────┐
                     │                MANUAL REVIEW QUEUE                    │
                     │         ← Human decides: Approve / Skip / Expire →   │
                     └─────────────────────────────────────────┬────────────┘
                                                               │ (if approved)
                                          ┌────────────────────▼────────────┐
                                          │  EXECUTION PREP                  │
                                          │  (data-only readiness checks)    │
                                          └────────────────────┬─────────────┘
                                                               │
                     ┌─────────────────────────────────────────▼────────────┐
                     │    HUMAN EXECUTES MANUALLY IN MT5 (system silent)    │
                     └─────────────────────────────────────────┬────────────┘
                                                               │
                                          ┌────────────────────▼────────────┐
                                          │  TRADE CAPTURE (READ ONLY)       │
                                          │  MT5 fills linked to tickets     │
                                          └────────────────────┬─────────────┘
                                                               │
                         ┌─────────────────────────────────────▼────────────┐
                         │  TRADE MANAGEMENT ASSISTANT                       │
                         │  Suggestions only: SL, TP1, TP2, close           │
                         └─────────────────────────────────────┬─────────────┘
                                                               │
   ┌──────────────────────────────────────────────────────────▼────────────┐
   │  JOURNAL → HINDSIGHT → DAILY/WEEKLY REPORTS → CALIBRATION → TUNING   │
   └──────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                               PILOT GATE (graduation criteria)
```

---

### Component Reference

#### 1. Ingestion Service

- **Input**: Calendar events (news), macro proxy data (DXY, US10Y), raw market
  data.
- **Output**: `MarketContextPacket` — a snapshot of current market conditions,
  including high-impact events and no-trade windows.
- **Why it exists**: Everything else in the system needs to know *what is
  happening in the world right now* before making any decision.

#### 2. Fundamentals Engine

- **Input**: `MarketContextPacket`, processed intel on USD strength/weakness.
- **Output**: `PairFundamentalsPacket` — a bias packet for each currency pair
  (e.g., "USD is bullish today").
- **Why it exists**: No trade setup should contradict the macro environment. If
  the fundamentals say USD is strong, the system should not be taking trades
  betting against it.

#### 3. Technical Scanner (PHX)

- **Input**: Live price data, `PairFundamentalsPacket`.
- **Output**: `TechnicalSetupPacket` — a scored, staged setup with entry, SL,
  TP coordinates.
- **Why it exists**: This is the core "signal generator" — it tracks the PHX
  stage model and only fires a signal when all stages are complete.

#### 4. Guardrails Engine

- **Input**: `TechnicalSetupPacket`, `MarketContextPacket`, account state.
- **Output**: `GuardrailsResult` — a pass/fail/warn for 7 rules, plus a
  `hard_block` flag.
- **Rules checked** (GR-S01 to GR-Q01):
  - Session window (is the market in an active session?)
  - End-of-Day broker gap (avoid broker rollover spread widening)
  - News window (is there a red-folder event within 30 minutes?)
  - PHX sequence completeness (did the setup reach the minimum stage?)
  - Displacement quality (was the move decisive?)
  - Setup score (is the score above the minimum threshold?)
  - Risk state (too many consecutive losses? Daily loss limit hit?)
- **Safety boundary**: A `hard_block` from Guardrails **overrides** any Risk
  Engine `ALLOW`. It cannot be bypassed.

#### 5. Risk Engine

- **Input**: `TechnicalSetupPacket`, `MarketContextPacket`, account state.
- **Output**: `RiskApprovalPacket` — ALLOW or BLOCK, with reasons.
- **Why it exists**: A second independent layer of financial risk checks (RR
  ratio, drawdown limits, event window timing).

#### 6. Ticket Generator

- **Input**: Approved `RiskApprovalPacket` + setup data.
- **Output**: `OrderTicket` — a human-readable trade proposal with all
  parameters (pair, direction, entry, SL, TP1, TP2, score, expiry time).
- **Safety boundary**: A ticket is a **data object only**. It has no ability to
  execute anything.

#### 7. Manual Review Queue

- **Input**: Open `OrderTicket` records with status `IN_REVIEW`.
- **Output**: Human decision: `APPROVE`, `SKIP`, or tickets auto-expire.
- **Why it exists**: You are the final gate. Nothing moves forward without
  your explicit approval.
- **Safety boundary**: All decisions are logged with timestamps and reasons.

#### 8. Execution Prep

- **Input**: Approved `OrderTicket`.
- **Output**: `ExecutionPrepSchema` — a checklist of PASS/WARN/FAIL for
  readiness (price tolerance, spread, news proximity, kill switch, expiry).
- **Why it exists**: Before you manually enter a trade at your broker, the
  system runs a final sanity check on current conditions.
- **Safety boundary**: FAIL-CLOSED. If live quotes are missing or stale, it
  fails the check. You cannot get a "green light" on bad data.

#### 9. Trade Capture (READ-ONLY)

- **Input**: MT5 trade fills and open positions via the Bridge service.
- **Output**: `TradeFillLog`, `PositionSnapshot` — stored records linked to
  tickets.
- **Why it exists**: The system needs to know what you actually executed so it
  can score your decisions, calculate R, and feed the journal.
- **Safety boundary**: No `OrderSend` or trading API calls exist anywhere in
  the codebase. This service only *reads* from MT5.

#### 10. Trade Management Assistant

- **Input**: Open `PositionSnapshot`, live quotes.
- **Output**: `ManagementSuggestionLog` — rule-based suggestions (Move SL to
  BE, Take TP1, Close before news, etc.).
- **Why it exists**: Provides real-time, rule-based guidance so you don't make
  emotional decisions (e.g., moving SL further because you "feel" the trade
  will reverse).
- **Safety boundary**: Suggestions only. The system never modifies a broker
  order.

#### 11. Journal

- **Input**: Trade fills, outcomes, decisions.
- **Output**: `JournalLog` — a structured, append-only log of all events
  (ticket created, approved, trade opened, partial close, full close).
- **Why it exists**: Provides the audit trail for all downstream analysis.

#### 12. Hindsight Engine

- **Input**: Skipped/expired tickets, historical price data.
- **Output**: Hindsight simulations — "What R would you have made if you had
  taken this trade?"
- **Why it exists**: Helps you understand the *cost* of skipping a trade. High
  "missed R" may mean your skip policy is too conservative.

#### 13. Reports (Daily / Weekly)

- **Input**: Journal, tickets, hindsight, incidents.
- **Output**: Structured HTML reports — actionable summaries of system
  performance.
- **Why it exists**: Forces a daily and weekly review habit.

#### 14. Calibration & Tuning

- **Input**: Historical run data, research simulations.
- **Output**: Parameter proposals — suggestions such as "increase min RR from
  2.0 to 2.5 based on last 30 sessions."
- **Why it exists**: The system continuously evaluates its own rules and
  proposes data-driven improvements.

#### 15. Pilot Gate

- **Input**: `PilotScorecardLog` — real session metrics from the journal.
- **Output**: PASS/FAIL against graduation thresholds.
- **Why it exists**: Before increasing capital, the Pilot Gate ensures the
  system has proven itself across a meaningful sample of sessions. It forces
  you to earn the next level.

---

## SECTION C — How to Run It

### Minimum Commands (Local Development)

```bash
# 1. Ensure dependencies are installed
pip install -r requirements.txt

# 2. Initialize the database (first time only)
alembic upgrade head

# 3. Seed sample data (optional, for testing)
python seed_db.py

# 4. Start the dashboard server
python services/dashboard/main.py
# Dashboard will be available at: http://localhost:8005/dashboard
```

For production (Docker Compose):
```bash
docker-compose up --build -d
```

---

### How to Verify Health & Integration Readiness

```bash
python -m infra.cli infra status
```

**What "healthy" looks like:**

```text
+-----------------------------------------------------------+
| Provider Type | Active Implementation  | Env Var | Status |
|---------------+------------------------+---------+--------|
| Calendar      | ForexFactoryCalendar   | set     | OK     |
| Proxy         | RealProxyProvider      | set     | OK     |
| Price Quote   | DBPriceQuoteProvider   | set     | OK     |
| Symbol Spec   | DBSymbolSpecProvider   | set     | OK     |
+-----------------------------------------------------------+
Redis:  Connected
```

> ⚠️ **In development**, all providers will show `MOCK` — this is normal and safe. `MOCK` providers are **forbidden** in `ENV=prod`.

---

### What To Do If Something Is Stale or Broken

| Symptom | Likely Cause | Action |
|---|---|---|
| All providers show `MOCK` | Env vars not set | Set `CALENDAR_PROVIDER`, `PROXY_PROVIDER`, etc. in `.env` |
| Redis: NOT CONNECTED | Redis server is down | Start Redis: `redis-server` |
| `DATABASE_URL: MISSING` | `.env` not loaded | Verify `.env` file exists with correct values |
| Quote staleness warning in dashboard | MT5 Bridge offline | Restart the Bridge service or check MT5 connection |
| Tickets not appearing in queue | Technical Service down | Check `python -m infra.cli infra status` for wiring health |
| Daily report missing | Report not generated yet | Run orchestration service or check `artifacts/ops/` directory |

---

## SECTION D — How to Use It (Daily Operator Tutorial)

*Let's walk through a complete trading day together.*

---

### Step 1 — Open the Dashboard: Read the Status Bar
**URL**: `http://localhost:8005/dashboard`

*Screenshot: Dashboard overview — top status bar with session indicator, live quote freshness, kill switches.*

The very first thing you do is look at the top of the overview page:

- **Session Label**: Is London or New York active? If it shows "OFF-HOURS
  (ASIA)", you probably shouldn't be looking for trades yet.
- **Live Quotes**: Are live quotes from the Bridge fresh (< 30 seconds)? A red
  indicator here means the price feed is stale.
- **Kill Switches**: Are any active? An active kill switch means trading is
  halted system-wide. Do not override without understanding why it was
  triggered.
- **Next Red Event**: Is there a high-impact news event coming up in the next
  60 minutes? Build this awareness before you do anything.

---

### Step 2 — Read the Daily Ops Report & Session Briefing
**URL**: `http://localhost:8005/dashboard/ops/daily`
**URL**: `http://localhost:8005/dashboard/briefings`

*Screenshot: Daily Ops report with session summary.*

The **Ops Report** shows you a structured summary of everything that happened since the last session: how many tickets were generated, how many were approved, approved vs. skipped outcomes, any incidents, and whether the system is healthy.

The **Session Briefing** is a narrative generated before the session begins — it includes macro context (is USD strong today?), the active policy (RISK_ON vs. RISK_OFF), and relevant events to watch out for.

**What to pay attention to:**

- Were there any `ERROR` or `CRITICAL` incidents? Investigate before trading.
- Is the active policy what you expect? If it shows `RISK_OFF`, the system will
  be more conservative.
- What time is the next red-folder event? Block that window out mentally.

---

### Step 3 — Work the Queue
**URL**: `http://localhost:8005/dashboard/queue`

*Screenshot: Queue page with IN_REVIEW tickets, guardrails score, and action buttons.*

The **Queue** is the heart of your daily workflow. This is where tickets waiting for your review appear.

**What "IN_REVIEW" means**: The system has found a setup that passed all automated checks and is now asking for your human judgment.

**What you see for each ticket:**
- Pair (e.g., GBPJPY)
- Direction (BUY or SELL)
- Entry price, Stop Loss, Take Profit 1, Take Profit 2
- Guardrails score (0–100) — higher is better
- Expiry time — the ticket is time-limited. If it expires, it's gone.

**How to Approve:**
Click `APPROVE`. The ticket will move to `APPROVED` status, and an **Execution Prep** packet will be generated automatically.

> ✅ Approve when: the setup aligns with your session bias, no recent news, guardrails score is high, and the RR is clean.

**How to Skip:**

Click `SKIP` and select a reason:

- `NEWS_PROXIMITY` — news event within 30 mins
- `SPREAD_WIDE` — the spread is too wide to trade safely
- `OPERATOR_DISCRETION` — you simply don't like the setup

> ⏩ Skip when: your gut says the context doesn't feel right, or conditions
> don't meet your personal criteria beyond the automated checks.

**About Ticket Expiry:**

Tickets expire because market conditions change. A setup that was valid at
11:00 EAT may be invalid by 13:00 EAT. The system automatically expires stale
tickets and logs them for Hindsight analysis.

---

### Step 4 — Check Execution Prep
**URL**: Accessible from the approved ticket in the queue, or via `GET /api/execution-prep/{ticket_id}`

*Screenshot: Execution Prep panel with PASS/WARN/FAIL checks.*

Once you approve a ticket, the system runs a final pre-flight check called **Execution Prep**. It verifies:

| Check | PASS | WARN | FAIL |
|---|---|---|---|
| Ticket Expiry | Active | — | Expired |
| Kill Switch | None active | — | Active |
| Price Tolerance | Entry price still valid | — | Price moved too far |
| Spread | Within max (3 pips) | Slightly wide | Unavailable data |
| News Window | No event nearby | — | Within buffer window |

**What FAIL CLOSED means here:**
If the live price cannot be retrieved (e.g., the bridge is down), the system marks `FAIL` — it does **not** assume the price is still valid. No green light on bad data.

**When is an override allowed?**

In exceptional circumstances (e.g., a confirmed connectivity blip that is
already resolved), you can override an Execution Prep check by providing a
written reason. This reason is **logged permanently**. The Operator Manual
states: "Manual overrides should be rare. Never override SL/TP to increase
risk."

---

### Step 5 — Execute Manually in MT5
*This step happens entirely outside the system.*

The system provides you with all the parameters: Entry, Stop Loss, Take Profit 1, Take Profit 2, and lot size. You open MT5, navigate to your symbol, and place the order manually.

**Critical step — use the comment field:**

In your MT5 order, set the **comment** to the ticket ID (e.g.,
`TKT-20260303-001`). This is how the Trade Capture service links your fill
back to the original ticket. Without this, the fill will be "unmatched" in the
system.

> 🔒 **The system never sends an order to MT5.** No API call, no automation.
> You are the one who clicks "Buy" or "Sell."

---

### Step 6 — Verify Trade Capture
**URL**: `http://localhost:8005/dashboard/trades`

*Screenshot: Trades page showing fills and matched ticket links.*

After you execute in MT5, the Bridge service picks up the fill and writes it to the database. You should see your trade appear in the Trades dashboard within 1–2 minutes.

**What to check:**

- Does the fill appear? (If not, wait a moment and refresh.)
- Is it **matched** to a ticket? You'll see the ticket ID displayed alongside
  the fill.
- If it's **unmatched**: you likely forgot the comment field. You can manually
  link it via the API if needed.

---

### Step 7 — Monitor Trade Management Suggestions
**URL**: `http://localhost:8005/dashboard/management`

*Screenshot: Management page with active suggestions.*

While a trade is running, the Trade Management Assistant monitors it and generates suggestions:

- **"Move SL to BE"** (Move Stop Loss to Break-Even): When the trade has moved
  1R in your favour, the system suggests moving your stop loss to your original
  entry price. This locks in a "no-loss" outcome at minimum.
- **"Take Partial TP1"**: When price hits your first take-profit level, the
  system suggests closing half the position.
- **"Close Before News"**: If a high-impact event is approaching, the system
  suggests closing the position to avoid news-driven volatility.
- **"End of Session Close"**: If it's approaching 01:00 EAT (NY session close),
  the system suggests closing any open positions.

> ⚠️ These are **suggestions only**. The system does not modify your broker
> position. You execute each suggestion manually in MT5.

---

### Step 8 — End of Day Review
**URL**: `http://localhost:8005/dashboard/hindsight`

*Screenshot: Hindsight page showing missed vs. realized R.*

At the end of your session:

1. **Check Journal** — `http://localhost:8005/dashboard/tickets` — confirm all
   open trades have been resolved (closed, or still running with clear notes).
2. **Check Hindsight** — See what R was realized vs. what was available on
   skipped/expired tickets. Did you make the right call on what you skipped?
   Did you miss a clean setup?
3. **Check Incidents** — `http://localhost:8005/dashboard/incidents` — were
   there any system errors or warnings today you should address before
   tomorrow?

---

## SECTION E — The Weekly Improvement Loop

Every Friday after the session closes, you run the Weekly Cycle.

### Weekly Review Pack
**URL**: `http://localhost:8005/dashboard/ops/weekly`

The **Weekly Report** is a narrative summary of the last 5 trading sessions. It shows:
- Total tickets generated vs. approved vs. skipped
- Overall expectancy (the average R per trade)
- Override rate (how often did you override the system's recommendation?)
- Incident count
- Worst single session (to investigate)

### Calibration & Tuning Proposals
**URL**: `http://localhost:8005/dashboard/calibration` · `http://localhost:8005/dashboard/tuning`

The **Calibration** dashboard shows research runs that simulate how the
strategy has performed under different parameter settings. The **Tuning**
dashboard turns these simulations into actionable **Proposals** — concrete
recommendations like "raise the minimum setup score from 70 to 75."

**How to evaluate a proposal:**

1. Run the counterfactual simulation: `python -m infra.cli research
   validate-proposals --id <ID>` to see the simulated improvement.
2. Review the proposal in the dashboard.
3. Click `ACCEPT` or `REJECT`. Your decision is logged.
4. If accepted, apply the YAML patch provided (the UI will guide you).
5. To roll back: restore the previous config from `backups/`.

> ⚠️ Never accept a proposal that increases risk limits (larger position sizes,
> wider SL, lower min-RR) without very strong evidence.

---

### Pilot Gate
**URL**: `http://localhost:8005/dashboard/pilot` · `http://localhost:8005/dashboard/pilot/gate`

The **Pilot Gate** is the graduation system. Before you can increase your
position sizes or move from a pilot to a live account, the system requires you
to prove consistent performance across a rolling window of sessions.

**Graduation thresholds (from `OPERATOR_MANUAL.md`):**

| Metric | Required Value | Plain English Meaning |
|---|---|---|
| Quote Staleness | < 30 seconds | Your data feed is reliable |
| Max Overrides | 1 per session | You trust the system, not just yourself |
| Median Review Time | < 300 seconds | You're not leaving tickets to expire |
| Min Approved Trades | 8 trades | Enough data to measure |
| Expectancy Delta | > 0.03R above baseline | Your decisions add value |
| Session Drawdown | > -2.0R | No blowout sessions |
| Win Rate | > 40% | Sustainable psychologically |

If the Pilot Gate fails, it's not a punishment — it's a signal. The system
tells you which metric failed and why. Use Hindsight and Calibration to
investigate.

---

## SECTION F — Glossary

| Term | Plain English Meaning |
| :--- | :--- |
| **Pair** | A currency combination (e.g., GBPJPY = British Pound vs. Japanese Yen). The price tells you how much of one currency buys the other. |
| **Spread** | The gap between the buy price and sell price. The broker's fee. Wider spread = more cost to you. |
| **Lot Size** | The volume of a trade. 0.01 lots is a "micro lot" — a very small position. 1.0 lot is a "standard lot" — much larger. |
| **SL (Stop Loss)** | A price level where the trade automatically closes to limit your loss. Non-negotiable — always set before entering. |
| **TP (Take Profit)** | A price level where the trade automatically closes to lock in a gain. TP1 = first target, TP2 = final target. |
| **R-multiple** | Your risk unit. If you risk $100 to make $200, that's 2R. It's a universal way to measure trade quality regardless of account size. |
| **Expectancy** | Your average R per trade over a sample. If it's positive (>0), your strategy has edge. Below 0.05R and you're barely breaking even. |
| **Drawdown** | The depth of a losing streak. If your account went from $1000 to $900, that's a 10% drawdown or -1R. |
| **Risk-Off / Risk-On** | Regime labels. Risk-ON = market is calm, take full setups. Risk-OFF = market is volatile, be more selective, take profits earlier. |
| **Ticket** | The system's trade proposal — a data document containing all the parameters for a potential trade. Not an order. |
| **Queue** | The list of tickets waiting for your human review and approval. |
| **Preflight** | The final safety check before you manually execute a ticket in MT5. Similar to a pilot's pre-takeoff checklist. |
| **Trade Capture** | The process of reading MT5 fills into the system — completely passive and read-only. |
| **Idempotency** | If the same event fires twice (e.g., a duplicate webhook), the system does not create a duplicate ticket or journal entry. Safe by design. |
| **Staleness** | The age of data. A live price that is 60 seconds old is "stale." A market context that is 3 hours old is stale. Stale data triggers warnings or blocks. |
| **Fail Closed** | If a safety check cannot be completed due to missing data, the system rejects the action (rather than guessing and proceeding). |

---

## SECTION G — Quickstart Cheat Sheet

```text
╔══════════════════════════════════════════════════════════╗
║          TH TRADING SYSTEM — DAILY CHEAT SHEET          ║
╠══════════════════════════════════════════════════════════╣
║  1. BEFORE YOU START (Morning)                          ║
║    → Check: http://localhost:8005/dashboard             ║
║    → Is the session active? (London starts ~11:00 EAT)  ║
║    → Are live quotes fresh? (< 30s)                     ║
║    → Any kill switches on? (Fix before proceeding)      ║
║    → Read daily report: /dashboard/ops/daily            ║
║                                                          ║
║  2. WORKING THE QUEUE                                   ║
║    → Go to: /dashboard/queue                            ║
║    → Review each IN_REVIEW ticket                       ║
║    → APPROVE if conditions are right                    ║
║    → SKIP with a reason if not                         ║
║    → Watch expiry times! Tickets expire.               ║
║                                                          ║
║  3. BEFORE EXECUTING IN MT5                             ║
║    → Check Execution Prep: all checks PASS?             ║
║    → Set MT5 comment to the ticket ID                   ║
║    → Execute manually (system does NOT place orders)    ║
║                                                          ║
║  4. WHILE TRADE IS RUNNING                              ║
║    → Check: /dashboard/management for suggestions      ║
║    → Execute Move SL/TP manually if suggested           ║
║    → Watch for news events incoming                     ║
║                                                          ║
║  5. END OF SESSION                                      ║
║    → Check: /dashboard/hindsight                       ║
║    → Check: /dashboard/incidents for errors            ║
║    → Check: /dashboard/trades for unmatched fills      ║
╠══════════════════════════════════════════════════════════╣
║  IF SOMETHING LOOKS RED                                  ║
║    • Red quote indicator → restart Bridge service       ║
║    • Kill switch on → investigate before trading        ║
║    • No tickets in queue → check if Technical Service   ║
║      is running and market is in session                ║
║    • Execution Prep FAIL → DO NOT trade, diagnose first ║
╚══════════════════════════════════════════════════════════╝
```

---

### Dashboard Routes Reference

| Dashboard Page | URL |
| :--- | :--- |
| Main Overview | `/dashboard` |
| Queue (Manual Review) | `/dashboard/queue` |
| All Tickets | `/dashboard/tickets` |
| Ops Daily Report | `/dashboard/ops/daily` |
| Ops Weekly Report | `/dashboard/ops/weekly` |
| Live Trades & Fills | `/dashboard/trades` |
| Trade Management | `/dashboard/management` |
| Hindsight Analysis | `/dashboard/hindsight` |
| Session Briefings | `/dashboard/briefings` |
| Fundamentals | `/dashboard/fundamentals` |
| Risk Decisions | `/dashboard/risk` |
| Policies | `/dashboard/policies` |
| Calibration | `/dashboard/calibration` |
| Tuning Proposals | `/dashboard/tuning` |
| Pilot Scorecard | `/dashboard/pilot` |
| Pilot Gate Thresholds | `/dashboard/pilot/gate` |
| Research Runs | `/dashboard/research` |
| Action Items | `/dashboard/action-items` |
| Incidents Log | `/dashboard/incidents` |

---

## Reality Check

> This section lists features that require real external configuration and will not function in a plain development environment without the corresponding credentials.

| Feature | Status Without Config | How to Enable |
| :--- | :--- | :--- |
| Calendar events (news gating) | Uses `MockCalendarProvider` — deterministic fake events | Set `CALENDAR_PROVIDER=forexfactory` and `FOREX_FACTORY_API_KEY` in `.env` |
| Macro proxy data (DXY, US10Y) | Uses `MockProxyProvider` — static fake data | Set `PROXY_PROVIDER=real` and `TWELVE_DATA_API_KEY` |
| Live price quotes | Uses `MockPriceQuoteProvider` | Set `PRICE_PROVIDER=db` and run the MT5 Bridge service |
| Telegram notifications | Disabled — no alerts sent | Set `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` |
| Redis stream wiring | Services cannot communicate via streams | Start a Redis instance: `docker run -p 6379:6379 redis` |
| Production provider enforcement | In `ENV=development`, mocks are silently allowed | Set `ENV=prod` to enforce fail-closed provider validation |

**Files referenced to verify this guide:**

- `services/dashboard/main.py` — all routes confirmed
- `docs/OPERATOR_MANUAL.md` — Pilot Gate thresholds
- `docs/PROVIDER_MAP.md` — provider configurations
- `docs/INTEGRATIONS.md` — integration setup
- `docs/RELEASE_CHECKLIST.md` — verification commands
- `shared/logic/guardrails.py` — 7 rules (GR-S01 to GR-Q01)
- `shared/logic/risk.py` — RR, drawdown, event window checks
- `shared/logic/execution_logic.py` — Execution Prep fail-closed logic
- `shared/logic/trade_management_engine.py` — suggestion rules
- `infra/cli.py` — CLI commands

---

### Guide Status

*Guide prepared: 2026-03-03 | Version: v1.0.0 | System: TH Trading System*
