from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date, timezone

import shared.database.session as db_session
from shared.database.models import OrderTicket, Packet
from shared.logic.trading_logic import generate_order_ticket
from shared.types.packets import TechnicalSetupPacket, RiskApprovalPacket
from shared.types.trading import OrderTicketSchema
import httpx

app = FastAPI(title="Orchestration Service API")

# Dependency
def get_db():
    db = db_session.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health():
    return {"status": "healthy", "service": "orchestration"}

@app.post("/tickets/generate", response_model=OrderTicketSchema)
async def generate_ticket(pair: str, db: Session = Depends(get_db)):
    """
    Finds the latest TechnicalSetupPacket + RiskApprovalPacket for a pair
    and generates a human-reviewable OrderTicket.
    """
    # 1. Fetch latest setup
    setup_db = db.query(Packet).filter(
        and_(Packet.packet_type == "TechnicalSetupPacket", Packet.data['asset_pair'].as_string() == pair)
    ).order_by(Packet.created_at.desc()).first()
    
    if not setup_db:
        raise HTTPException(status_code=404, detail=f"No technical setup found for {pair}")
    
    # 2. Fetch latest risk decision for this pair
    risk_db = db.query(Packet).filter(
        and_(Packet.packet_type == "RiskApprovalPacket", Packet.data['asset_pair'].as_string() == pair)
    ).order_by(Packet.created_at.desc()).first()
    
    if not risk_db:
        raise HTTPException(status_code=404, detail="No risk decision found for this setup.")

    # Convert DB data to models
    setup_packet = TechnicalSetupPacket(**setup_db.data)
    risk_packet = RiskApprovalPacket(**risk_db.data)

    # 3. Generate ticket
    ticket = generate_order_ticket(setup_packet, risk_packet, db)
    
    # Update IDs for traceability
    ticket.setup_packet_id = setup_db.id
    ticket.risk_packet_id = risk_db.id
    db.commit()
    
    # 4. Notify Journal Service
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://localhost:8004/log/ticket",
                json=OrderTicketSchema.model_validate(ticket, from_attributes=True).model_dump(mode='json'),
                params={"setup_id": setup_db.id, "risk_decision_id": risk_db.id}
            )
    except Exception as e:
        print(f"Failed to log ticket to Journal: {e}")
    
    return ticket

@app.get("/tickets/latest", response_model=OrderTicketSchema)
async def get_latest_ticket(pair: str, db: Session = Depends(get_db)):
    ticket = db.query(OrderTicket).filter(OrderTicket.pair == pair).order_by(OrderTicket.created_at.desc()).first()
    if not ticket:
        raise HTTPException(status_code=404, detail=f"No tickets found for {pair}")
    return ticket

@app.get("/tickets", response_model=List[OrderTicketSchema])
async def list_tickets(date_str: Optional[str] = Query(None, alias="date"), db: Session = Depends(get_db)):
    query = db.query(OrderTicket)
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            query = query.filter(db.func.date(OrderTicket.created_at) == d)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    return query.order_by(OrderTicket.created_at.desc()).all()

@app.patch("/tickets/{ticket_id}/status", response_model=OrderTicketSchema)
async def update_ticket_status(ticket_id: str, status: str, db: Session = Depends(get_db)):
    """Manual update: TAKEN / NOT_TAKEN."""
    if status not in ["TAKEN", "NOT_TAKEN", "PENDING"]:
        raise HTTPException(status_code=400, detail="Invalid status. Use TAKEN, NOT_TAKEN, or PENDING")
        
    ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    ticket.status = status
    db.commit()
    db.refresh(ticket)
    
    # Notify Journal of status change
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://localhost:8004/log/ticket",
                json=OrderTicketSchema.model_validate(ticket, from_attributes=True).model_dump(mode='json')
            )
    except Exception as e:
        print(f"Failed to update ticket in Journal: {e}")
        
    return ticket

from sqlalchemy import and_
