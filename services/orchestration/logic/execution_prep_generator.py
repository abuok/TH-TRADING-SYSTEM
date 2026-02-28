import uuid
from datetime import datetime, timedelta
from shared.database.models import OrderTicket, ExecutionPrepLog
from shared.types.execution_prep import ExecutionPrepSchema, PlatformFormats
from shared.logic.execution_logic import PreflightEngine, load_exec_config
from shared.logic.sessions import get_nairobi_time

class ExecutionPrepGenerator:
    def __init__(self, db):
        self.db = db
        self.config = load_exec_config()
        self.preflight = PreflightEngine(db)

    def generate(self, ticket: OrderTicket, current_price: float, current_spread: float) -> ExecutionPrepSchema:
        now = get_nairobi_time()
        ttl = self.config.get("ttl_seconds", 180)
        expires_at = now + timedelta(seconds=ttl)
        
        checks = self.preflight.run_checks(ticket, current_price, current_spread)
        override_required = any(c.status == "FAIL" for c in checks)
        
        formats = self.format_output(ticket)
        
        prep = ExecutionPrepSchema(
            prep_id=f"PREP_{uuid.uuid4().hex[:8]}",
            ticket_id=ticket.ticket_id,
            created_at=now,
            expires_at=expires_at,
            platform_formats=formats,
            preflight_checks=checks,
            price_tolerance_pct=self.config.get("price_tolerance_pct", 0.1),
            override_required=override_required
        )
        
        return prep

    def format_output(self, ticket: OrderTicket) -> PlatformFormats:
        mt5_tpl = self.config["platforms"]["mt5"]["format"]
        ctrader_tpl = self.config["platforms"]["ctrader"]["format"]
        
        mt5_text = mt5_tpl.format(
            id=ticket.ticket_id,
            pair=ticket.pair,
            dir=ticket.direction,
            lot=ticket.lot_size,
            entry=ticket.entry_price,
            sl=ticket.stop_loss,
            tp=ticket.take_profit_1
        )
        
        ctrader_text = ctrader_tpl.format(
            dir=ticket.direction,
            pair=ticket.pair,
            lot=ticket.lot_size,
            entry=ticket.entry_price,
            sl=ticket.stop_loss,
            tp1=ticket.take_profit_1,
            tp2=ticket.take_profit_2 or "N/A"
        )
        
        ticket_data = ticket.__dict__.copy()
        ticket_data.pop('_sa_instance_state', None)
        
        return PlatformFormats(
            mt5_text=mt5_text,
            ctrader_text=ctrader_text,
            json_data=ticket_data
        )
