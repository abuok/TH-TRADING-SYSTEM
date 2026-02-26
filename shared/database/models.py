from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Float
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()

class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, index=True, nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status = Column(String, default="running") # e.g., running, completed, failed
    
    packets = relationship("Packet", back_populates="run")

class Packet(Base):
    __tablename__ = "packets"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    packet_type = Column(String, index=True, nullable=False) # e.g., MarketContextPacket
    schema_version = Column(String, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    run = relationship("Run", back_populates="packets")

class KillSwitch(Base):
    __tablename__ = "kill_switches"

    id = Column(Integer, primary_key=True, index=True)
    switch_type = Column(String, nullable=False) # HALT_ALL, HALT_PAIR, HALT_SERVICE, HALT_EXECUTION
    target = Column(String, nullable=True) # e.g., BTCUSD or IngestionService
    is_active = Column(Integer, default=1) # 1 for active, 0 for inactive
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class IncidentLog(Base):
    __tablename__ = "incident_logs"

    id = Column(Integer, primary_key=True, index=True)
    severity = Column(String, index=True, nullable=False) # INFO, WARNING, ERROR, CRITICAL
    component = Column(String, index=True, nullable=False)
    error_code = Column(String, index=True)
    message = Column(String, nullable=False)
    context = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
