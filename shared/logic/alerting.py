"""
shared/logic/alerting.py
Logic for sending notifications on critical service events.
"""
import logging
import os
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("Alerting")

def send_critical_alert(service: str, event_type: str, details: Dict[str, Any]):
    """
    Sends a critical alert to the configured output (Console and Telegram).
    """
    timestamp = datetime.now().isoformat()
    alert_msg = f"<b>!!! CRITICAL ALERT [{service}] !!!</b>\n<b>Type:</b> {event_type}\n<b>Time:</b> {timestamp}\n<b>Details:</b> <code>{details}</code>"
    
    # 1. Console / File Log
    logger.critical(alert_msg.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
    
    # 2. Telegram Notification (Fire and Forget)
    import asyncio
    from shared.providers.alerting.telegram import TelegramProvider
    
    tp = TelegramProvider()
    try:
        # Note: In a production sync context, we'd use a background task or queue.
        # For simplicity here, we try to get the existing loop or create a temporary one.
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(tp.send_message(alert_msg))
            else:
                loop.run_until_complete(tp.send_message(alert_msg))
        except RuntimeError:
            asyncio.run(tp.send_message(alert_msg))
    except Exception as e:
        logger.error(f"Alerting: Telegram send failed - {e}")

def check_incident_alerts(incident_data: Dict[str, Any]):
    """
    Evaluates an incident for alert triggering.
    """
    severity = incident_data.get("severity", "INFO").upper()
    if severity in ["ERROR", "CRITICAL"]:
        send_critical_alert(
            service=incident_data.get("source", "UNKNOWN"),
            event_type=f"Incident: {severity}",
            details=incident_data
        )
