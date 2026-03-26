import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from fastapi import WebSocket, WebSocketDisconnect

from shared.messaging.event_bus import EventBus

logger = logging.getLogger("DashboardWS")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WS connection. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WS disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return
        
        payload = json.dumps(message)
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)
        
        for conn in dead_connections:
            self.disconnect(conn)

manager = ConnectionManager()

async def websocket_event_listener():
    """
    Background task that bridges Redis events to WebSocket clients.
    Listens for 'journal_events', 'market_updates', and 'incident_logs'.
    """
    bus = EventBus()
    
    # Track the last ID seen for each stream to only get NEW messages
    last_ids = {
        "journal_events": "$",
        "incident_logs": "$",
        "market_updates": "$"
    }
    
    logger.info("WebSocket Event Listener starting...")

    while True:
        try:
            # Poll Redis for new stream entries
            # Using xread (non-blocking or short blocking) to detect new data
            # format: {stream: last_id}
            response = bus.client.xread(last_ids, count=5, block=1000)
            
            if response:
                for stream_name, messages in response:
                    for msg_id, data_dict in messages:
                        # Update last_id for this stream
                        last_ids[stream_name] = msg_id
                        
                        # Extract and broadcast
                        try:
                            payload = json.loads(data_dict.get("payload", "{}"))
                            await manager.broadcast({
                                "type": "stream_update",
                                "stream": stream_name,
                                "message_id": msg_id,
                                "data": payload,
                                "server_ts": datetime.utcnow().isoformat()
                            })
                        except Exception as e:
                            logger.warning(f"Failed to parse or broadcast message {msg_id}: {e}")

            # Also broadcast a 30s heartbeat to prevent proxy timeouts
            if int(datetime.utcnow().timestamp()) % 30 == 0:
                await manager.broadcast({"type": "heartbeat", "ts": datetime.utcnow().isoformat()})
                await asyncio.sleep(1) # prevent multiple heartbeats in same second

            await asyncio.sleep(0.5) # Throttled check
            
        except Exception as e:
            logger.error(f"WebSocket Listener Loop Error: {e}")
            await asyncio.sleep(5)
