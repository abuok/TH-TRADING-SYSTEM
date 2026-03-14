"""
shared/logic/alerting.py
Logic for sending notifications on critical service events.
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("Alerting")


async def send_critical_alert(service: str, event_type: str, details: dict[str, Any]):
    """
    Sends a critical alert to the configured output (Console and Telegram).
    """
    timestamp = datetime.now().isoformat()
    alert_msg = f"<b>!!! CRITICAL ALERT [{service}] !!!</b>\n<b>Type:</b> {event_type}\n<b>Time:</b> {timestamp}\n<b>Details:</b> <code>{details}</code>"

    # 1. Console / File Log
    logger.critical(
        alert_msg.replace("<b>", "")
        .replace("</b>", "")
        .replace("<code>", "")
        .replace("</code>", "")
    )

    # 2. Telegram Notification (Fire and Forget/Asynchronous)
    from shared.providers.alerting.telegram import TelegramProvider

    tp = TelegramProvider()
    try:
        await tp.send_message_async(alert_msg)
    except Exception as e:
        logger.error(f"Alerting: Telegram send failed - {e}")


async def check_incident_alerts(incident_data: dict[str, Any]):
    """
    Evaluates an incident for alert triggering.
    """
    severity = incident_data.get("severity", "INFO").upper()
    if severity in ["ERROR", "CRITICAL"]:
        await send_critical_alert(
            service=incident_data.get("source", "UNKNOWN"),
            event_type=f"Incident: {severity}",
            details=incident_data,
        )
