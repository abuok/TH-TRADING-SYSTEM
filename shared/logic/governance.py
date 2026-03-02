import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import Session
from shared.database.models import KillSwitch, IncidentLog

logger = logging.getLogger("Governance")


class GovernanceEngine:
    def __init__(self, db: Session):
        self.db = db

    def is_halted(self, target_type: str, target_name: Optional[str] = None) -> bool:
        """
        Check if a specific target or the entire system is halted.
        target_type: HALT_ALL, HALT_PAIR, HALT_SERVICE, HALT_EXECUTION
        target_name: asset pair (e.g. BTCUSD) or service name
        """
        # Check for global halt first
        global_halt = (
            self.db.query(KillSwitch)
            .filter(KillSwitch.switch_type == "HALT_ALL", KillSwitch.is_active == 1)
            .first()
        )
        if global_halt:
            return True

        # Check for specific halt
        specific_halt = (
            self.db.query(KillSwitch)
            .filter(
                KillSwitch.switch_type == target_type,
                KillSwitch.target == target_name,
                KillSwitch.is_active == 1,
            )
            .first()
        )

        return specific_halt is not None

    def log_incident(
        self,
        severity: str,
        component: str,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[dict] = None,
    ):
        """Log a structured incident to the database."""
        incident = IncidentLog(
            severity=severity,
            component=component,
            message=message,
            error_code=error_code,
            context=context,
        )
        self.db.add(incident)
        self.db.commit()
        logger.warning(f"[{severity}] {component}: {message}")

    @staticmethod
    def is_stale(timestamp: datetime, ttl_seconds: int) -> bool:
        """Check if a packet is stale based on its timestamp and TTL."""
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        return now - timestamp > timedelta(seconds=ttl_seconds)

    def validate_packet_freshness(
        self, packet_type: str, timestamp: datetime, ttl_map: Dict[str, int]
    ) -> bool:
        """Validate packet freshness and log incident if stale."""
        ttl = ttl_map.get(packet_type, 60)  # Default 60s
        if self.is_stale(timestamp, ttl):
            self.log_incident(
                severity="ERROR",
                component="Orchestrator",
                message=f"Stale {packet_type} detected. Timestamp: {timestamp}",
                error_code="STALE_PACKET",
                context={
                    "packet_type": packet_type,
                    "timestamp": str(timestamp),
                    "ttl": ttl,
                },
            )
            return False
        return True
