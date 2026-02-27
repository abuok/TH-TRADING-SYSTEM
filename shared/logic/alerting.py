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
    Sends a critical alert to the configured output (Console for now, extendable to Telegram/Slack).
    """
    timestamp = datetime.now().isoformat()
    alert_msg = f"!!! CRITICAL ALERT [{service}] !!!\nType: {event_type}\nTime: {timestamp}\nDetails: {details}"
    
    # In production, this would use a notification adapter
    logger.critical(alert_msg)
    
    # Placeholder for external notification (e.g. Telegram API call)
    # if os.getenv("TELEGRAM_TOKEN"):
    #     ... 

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
