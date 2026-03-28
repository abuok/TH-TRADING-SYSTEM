"""
services/dashboard/worker.py
Background worker for the Dashboard Service.
Runs the MetricsAggregator to cache account stats in Redis.
"""

import asyncio
import logging
import signal
import sys
from shared.logic.metrics_aggregator import MetricsAggregator
from shared.config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("DashboardWorker")

class DashboardWorker:
    def __init__(self):
        self.aggregator = MetricsAggregator(interval_seconds=settings.METRICS_AGGREGATION_INTERVAL)
        self.is_running = False

    async def run(self):
        self.is_running = True
        logger.info("Dashboard Worker started. Aggregation interval: %ss", settings.METRICS_AGGREGATION_INTERVAL)
        
        try:
            await self.aggregator.run()
        except asyncio.CancelledError:
            logger.info("Dashboard Worker stopping...")
        except Exception as e:
            logger.error("Dashboard Worker encountered a fatal error: %s", e, exc_info=True)
        finally:
            self.is_running = False

    def stop(self):
        self.is_running = False
        self.aggregator.stop()

async def main():
    worker = DashboardWorker()
    
    # Handle termination signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop)

    await worker.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical("Failed to start Dashboard Worker: %s", e)
        sys.exit(1)
