import sys
import os
import time
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.technical.worker import TechnicalWorker

async def run_stress_test(num_quotes=5000, rps_target=500):
    print(f"Starting Stress Test: {num_quotes} quotes @ ~{rps_target} target RPS")
    
    worker = TechnicalWorker(pairs=["XAUUSD", "GBPJPY"])
    
    # Pre-generate quotes
    quotes = []
    for i in range(num_quotes):
        symbol = "XAUUSD" if i % 2 == 0 else "GBPJPY"
        quotes.append({
            "symbol": symbol,
            "bid": 2000.0 + (i % 10),
            "ask": 2001.0 + (i % 10),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    # Mock EventBus to return pre-generated quotes in chunks of 50
    chunk_size = 50
    quote_chunks = [quotes[i:i + chunk_size] for i in range(0, len(quotes), chunk_size)]
    
    # Prepare messages in Redis format: [(stream, [(msg_id, {"payload": json.dumps(data)})])]
    mock_messages = []
    for chunk in quote_chunks:
        msg_list = []
        for i, q in enumerate(chunk):
            msg_list.append((f"id_{i}", {"payload": json.dumps(q)}))
        mock_messages.append([("quote", msg_list)])
    
    # Add a final None to stop
    mock_messages.append(None)
    
    # Patch EventBus methods
    # We use list(mock_messages) to avoid side_effect exhausting the iterator if multiple calls happen
    # Actually, side_effect with a list is fine.
    with patch.object(worker.event_bus, "consume", side_effect=mock_messages), \
         patch.object(worker.event_bus, "subscribe", return_value=None), \
         patch.object(worker.event_bus.client, "xack", return_value=None), \
         patch.object(worker, "_publish_setup", return_value=None):
        
        start_time = time.time()
        
        worker_task = asyncio.create_task(worker.run())
        
        # Wait until consume has been called for all meaningful chunks
        # Total meaningful chunks = len(quote_chunks)
        # We also have one final None to trigger the loop exit or sleep
        while worker.event_bus.consume.call_count < len(quote_chunks):
            await asyncio.sleep(0.01)
            
        worker.stop()
        try:
            await asyncio.wait_for(worker_task, timeout=2.0)
        except asyncio.TimeoutError:
            worker_task.cancel()
        
        end_time = time.time()
        
    duration = end_time - start_time
    actual_rps = num_quotes / duration
    
    print(f"Stress Test Results:")
    print(f"  - Total Quotes: {num_quotes}")
    print(f"  - Duration: {duration:.2f}s")
    print(f"  - Actual Throughput: {actual_rps:.2f} quotes/sec")
    
    assert actual_rps >= 200, f"Throughput {actual_rps:.2f} is below target 200 RPS"
    print("STRESS TEST PASSED!")

if __name__ == "__main__":
    asyncio.run(run_stress_test())
