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

class OrderTicket(Base):
    __tablename__ = "order_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, unique=True, index=True, nullable=False)
    setup_packet_id = Column(Integer, ForeignKey("packets.id"), nullable=False)
    risk_packet_id = Column(Integer, ForeignKey("packets.id"), nullable=False)
    pair = Column(String, nullable=False)
    direction = Column(String, nullable=False) # BUY, SELL
    entry_type = Column(String, default="MARKET") # MARKET, LIMIT
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit_1 = Column(Float, nullable=False)
    take_profit_2 = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=False)
    risk_usd = Column(Float, nullable=False)
    risk_pct = Column(Float, nullable=False)
    rr_tp1 = Column(Float, nullable=False)
    rr_tp2 = Column(Float, nullable=True)
    status = Column(String, default="PENDING") # PENDING, TAKEN, NOT_TAKEN, BLOCKED
    block_reason = Column(String, nullable=True)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    setup_packet = relationship("Packet", foreign_keys=[setup_packet_id])
    risk_packet = relationship("Packet", foreign_keys=[risk_packet_id])
