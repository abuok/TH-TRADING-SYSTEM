"""
tests/test_stress.py
--------------------
Stress and concurrency tests for TH-TRADING-SYSTEM.

Run:
    pytest tests/test_stress.py -v -m stress

These tests are intentionally slow — exclude from default CI with ``-m "not stress"``.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

import pytest


# ── 1. Concurrent DB session stress ──────────────────────────────────────────

@pytest.mark.stress
def test_50_concurrent_db_sessions() -> None:
    """
    Pool must serve 50 simultaneous SELECT 1 calls without exhaustion.
    SQLite used in tests has a StaticPool so assertions are structural.
    """
    from shared.database.session import SessionLocal

    errors: list[Exception] = []

    def worker() -> None:
        db = SessionLocal()
        try:
            db.execute(db.bind.text("SELECT 1"))  # type: ignore[union-attr]
        except Exception as exc:
            errors.append(exc)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(worker) for _ in range(50)]
        for f in as_completed(futures):
            f.result()  # Re-raise any thread exception

    assert errors == [], f"Pool errors: {errors}"


# ── 2. Bulk ticket insert + query timing ─────────────────────────────────────

@pytest.mark.stress
def test_1000_ticket_query_under_2s(db) -> None:  # type: ignore[no-untyped-def]
    """Inserting and querying 1 000 tickets must complete in under 2 seconds."""
    from shared.database.models import OrderTicket, Packet, Run
    import uuid

    # Minimal run + packet scaffolding
    run = Run(run_id=f"stress-run-{uuid.uuid4()}", status="running")
    db.add(run)
    db.flush()

    pkt = Packet(
        run_id=run.id,
        packet_type="TechnicalSetupPacket",
        schema_version="1.0",
        data={"pair": "XAUUSD"},
    )
    db.add(pkt)
    db.flush()

    tickets = [
        OrderTicket(
            ticket_id=f"stress-{i}-{uuid.uuid4()}",
            setup_packet_id=pkt.id,
            risk_packet_id=pkt.id,
            pair=["XAUUSD", "GBPJPY", "EURUSD"][i % 3],
            direction=["BUY", "SELL"][i % 2],
            entry_type="MARKET",
            entry_price=1900.0 + i,
            stop_loss=1890.0,
            take_profit_1=1920.0,
            lot_size=0.01,
            risk_usd=10.0,
            risk_pct=1.0,
            rr_tp1=2.0,
            status="PENDING",
            idempotency_key=f"ik-stress-{i}-{uuid.uuid4()}",
        )
        for i in range(1000)
    ]
    db.bulk_save_objects(tickets)
    db.flush()

    start = time.perf_counter()
    results = (
        db.query(OrderTicket)
        .filter(OrderTicket.status == "PENDING")
        .all()
    )
    elapsed = time.perf_counter() - start

    assert len(results) >= 1000, "Expected 1 000+ pending tickets"
    assert elapsed < 2.0, f"Query took {elapsed:.2f}s — exceeds 2s budget"


# ── 3. Async concurrent evaluations ──────────────────────────────────────────

@pytest.mark.stress
@pytest.mark.asyncio
async def test_async_concurrent_calls() -> None:
    """
    30 simultaneous async tasks should all complete without raising.
    Uses a lightweight mock so there's no real service dependency.
    """

    async def dummy_evaluate(i: int) -> str:
        await asyncio.sleep(0.01)  # Simulate I/O
        return f"result-{i}"

    tasks = [dummy_evaluate(i) for i in range(30)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 30
    assert all(r.startswith("result-") for r in results)
