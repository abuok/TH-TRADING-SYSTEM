import asyncio
import logging
import os
import requests
from datetime import datetime, timezone, timedelta

from shared.logic.notifications import NotificationService, ConsoleNotificationAdapter
from shared.types.packets import Candle
from runner import Orchestrator
from shared.database.session import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DemoRunner")


class DemoRunner:
    def __init__(self, dry_run: bool = True):
        self.risk_config = {
            "max_daily_loss": 30.0,
            "max_total_loss": 100.0,
            "max_consecutive_losses": 2,
            "min_rr_threshold": 2.0,
            "lot_size_limit": 0.1,
            "account_balance": 1000.0,
        }
        self.notifier = NotificationService([ConsoleNotificationAdapter()])
        self.orchestrator = Orchestrator(
            self.risk_config, dry_run=dry_run, notifier=self.notifier
        )
        self.asset_pair = "BTCUSD"

    async def run_e2e_flow(self):
        logger.info("--- STARTING E2E DEMO ---")
        self.notifier.notify("Initializing System V1 Demo...", level="INFO")

        # 1. Initialize Database
        init_db()

        # 2. Pre-session Briefing
        historical_candles = [
            Candle(
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                open=60000.0,
                high=61000.0,
                low=59000.0,
                close=60500.0,
                volume=1.0,
            )
            for i in range(10)
        ]
        await self.orchestrator.pre_session_briefing(
            self.asset_pair, historical_candles
        )

        # 3. Simulate Technical Replay / Live Loop
        # The live_loop will:
        # - Get latest context
        # - Scan for setup (mocked to hit)
        # - Evaluate risk
        # - Generate Decision Packet & Notify
        await self.orchestrator.live_loop(self.asset_pair)

        # 4. Log to Journal Service (Simulated API call if service is up, or direct DB/Logic for demo)
        # For simplicity in demo, we hit the local Journal endpoints if possible,
        # but since this script might run standalone, we'll assume Journal is reachable.
        try:
        journal_url = "http://localhost:8004"  # Journal service (compose port 8004)
            setup_id = 1  # Assume first setup

            # Log an outcome manually to prove the journal works
            logger.info("Simulating manual trade outcome entry...")
            res = requests.post(
                f"{journal_url}/log/outcome?setup_id={setup_id}&is_win=True&r_multiple=3.0&pnl=150.0"
            )
            if res.status_code == 200:
                logger.info("Successfully logged trade outcome to Journal Service.")
        except Exception as e:
            logger.warning(
                f"Could not reach Journal Service API ({e}). Skipping outcome log."
            )

        # 5. Generate Daily Report
        logger.info("Generating Daily Report...")
        try:
            report_res = requests.get(f"{journal_url}/report/daily")
            if report_res.status_code == 200:
                os.makedirs("artifacts", exist_ok=True)
                with open("artifacts/daily_report.html", "w") as f:
                    f.write(report_res.text)
                logger.info("Daily Report generated: artifacts/daily_report.html")
                self.notifier.notify(
                    "E2E Demo Complete. Report Ready.", level="SUCCESS"
                )
        except Exception as e:
            logger.warning(f"Could not generate report from Journal Service ({e}).")


if __name__ == "__main__":
    runner = DemoRunner(dry_run=True)
    asyncio.run(runner.run_e2e_flow())
