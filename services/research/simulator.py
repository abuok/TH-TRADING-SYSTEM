import csv
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional
import uuid

from shared.types.packets import Candle, TechnicalSetupPacket, RiskApprovalPacket
from shared.types.trading import OrderTicketSchema
from shared.types.research import SimulatedTrade, CounterfactualConfig, ResearchRunResult, ResearchVariant
from shared.logic.fundamentals_engine import evaluate_fundamentals
from shared.logic.guardrails import GuardrailsEngine, GuardrailsResult, load_config
from shared.logic.policy_router import PolicyRouter

from services.research.outcome import simulate_outcome
from services.research.analytics import calculate_metrics

def _parse_csv(filepath: str) -> List[Candle]:
    candles = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Expected headers: timestamp (ISO), open, high, low, close, volume
            dt = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            candles.append(Candle(
                timestamp=dt,
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume'])
            ))
    return sorted(candles, key=lambda c: c.timestamp)

def _mock_detector(candles: List[Candle], pair: str, timeframe: str) -> Optional[TechnicalSetupPacket]:
    """
    A naive mock detector for the sake of the Replay Engine.
    In a real system, this would call the actual PHX detector logic over the historical window.
    Here we just look for a simple consecutive 3-candle momentum pattern to trigger a mock setup.
    """
    if len(candles) < 3:
        return None
        
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    
    # Simple Bullish 3-drive mock
    if c1.close > c1.open and c2.close > c2.open and c3.close > c3.open:
        return TechnicalSetupPacket(
            schema_version="1.0.0",
            asset_pair=pair,
            strategy_name="MOCK_PHX_BULL",
            entry_price=c3.close,
            stop_loss=c3.close - (c3.high - c3.low) * 2, # 2 ATR approx
            take_profit=c3.close + (c3.high - c3.low) * 4, # 1:2 RR
            timeframe=timeframe,
            timestamp=c3.timestamp
        )
        
    # Simple Bearish 3-drive mock
    if c1.close < c1.open and c2.close < c2.open and c3.close < c3.open:
        return TechnicalSetupPacket(
            schema_version="1.0.0",
            asset_pair=pair,
            strategy_name="MOCK_PHX_BEAR",
            entry_price=c3.close,
            stop_loss=c3.close + (c3.high - c3.low) * 2,
            take_profit=c3.close - (c3.high - c3.low) * 4,
            timeframe=timeframe,
            timestamp=c3.timestamp
        )
        
    return None

def run_replay(
    csv_path: str,
    pair: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    variants: Dict[str, CounterfactualConfig]
) -> ResearchRunResult:
    
    run_id = f"res_{uuid.uuid4().hex[:8]}"
    candles = _parse_csv(csv_path)
    
    # Filter by date range
    if start_date.tzinfo is None: start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None: end_date = end_date.replace(tzinfo=timezone.utc)
    
    valid_candles = [c for c in candles if start_date <= c.timestamp <= end_date]
    
    if not valid_candles:
        raise ValueError("No candles found in specified date range.")
    
    result = ResearchRunResult(
        run_id=run_id,
        pair=pair,
        start_date=valid_candles[0].timestamp,
        end_date=valid_candles[-1].timestamp,
        timeframes=[timeframe]
    )
    
    for variant_name, config_override in variants.items():
        variant_trades: List[SimulatedTrade] = []
        
        # Build modified config
        gc = load_config()
        if config_override.min_setup_score is not None:
            gc["min_setup_score"] = config_override.min_setup_score
        if config_override.hard_block_displacement is not None:
            gc["displacement_quality_hard_block"] = config_override.hard_block_displacement
            
        # Sliding window simulation
        window_size = 50
        last_signal_time = None
        
        for i in range(window_size, len(valid_candles)):
            window = valid_candles[i-window_size:i]
            current_time = window[-1].timestamp
            
            # 1. Detector
            setup = _mock_detector(window, pair, timeframe)
            if not setup:
                continue
                
            # Duplicate suppression
            if last_signal_time:
                diff_mins = (current_time - last_signal_time).total_seconds() / 60.0
                suppression = config_override.duplicate_suppression_minutes or 60
                if diff_mins < suppression:
                    continue
                    
            last_signal_time = current_time
            
            # 2. Fundamentals (Mock generic ctx for replay)
            ctx = {
                "proxies": {
                    "SPX": {"symbol": "SPX", "current_value": 5000.0, "delta_pct": 0.5}, # Bullish risk-on baseline
                    "DXY": {"symbol": "DXY", "current_value": 104.0, "delta_pct": -0.2}  # Bearish DXY
                },
                "high_impact_events": []
            }
            movers, pair_packets = evaluate_fundamentals(ctx, current_time)
            bias_pkt = next((p for p in pair_packets if p.asset_pair == pair), None)
            bias_score = bias_pkt.bias_score if bias_pkt else 0.0
            
            # 3. Guardrails
            gr_engine = GuardrailsEngine()
            policy_config = gc
            policy_hash = None
            
            if config_override.use_router:
                from services.orchestration.main import _policy_router
                # In simulator, we'll instantiate if needed or use a mock
                # To avoid circular imports if _policy_router is in orchestration main
                from shared.logic.policy_router import PolicyRouter
                router = PolicyRouter()
                decision = router.select_policy(
                    movers_data=movers,
                    context_data=ctx,
                    pair_fundamentals=bias_pkt.model_dump() if bias_pkt else {},
                    now_nairobi=current_time
                )
                policy_config = decision.policy_config
                policy_hash = decision.policy_hash
            
            gr_res = gr_engine.evaluate(
                setup.model_dump(), 
                ctx, 
                None, 
                None, 
                current_time, 
                1,
                config_override=policy_config if config_override.use_router else None,
                policy_hash=policy_hash
            )
            
            # 4. Mock Risk & Ticket
            direction = "LONG" if "BULL" in setup.strategy_name else "SHORT"
            
            ticket = OrderTicketSchema(
                ticket_id=f"tkt_{uuid.uuid4().hex[:6]}",
                setup_packet_id=1,
                risk_packet_id=1,
                pair=pair,
                direction=direction,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                take_profit_1=setup.take_profit,
                lot_size=1.0,
                risk_usd=100.0,
                risk_pct=1.0,
                rr_tp1=abs(setup.take_profit - setup.entry_price) / abs(setup.entry_price - setup.stop_loss),
                idempotency_key=f"idem_{window[-1].timestamp.isoformat()}",
                created_at=current_time,
                status="BLOCKED" if gr_res.hard_block else "PENDING",
                block_reason=gr_res.primary_block_reason
            )
            
            sim_trade = SimulatedTrade(
                ticket_id=ticket.ticket_id,
                pair=pair,
                direction=direction,
                entry_price=ticket.entry_price,
                stop_loss=ticket.stop_loss,
                take_profit_1=ticket.take_profit_1,
                status=ticket.status,
                setup_score=85.0, # Mock high score
                bias_score=bias_score,
                guardrails_status="FAIL" if gr_res.hard_block else "PASS",
                stage=setup.strategy_name,
                block_reason=ticket.block_reason
            )
            
            # 5. Outcome Simulator
            future = valid_candles[i:] # The rest of the history
            sim_trade = simulate_outcome(sim_trade, future)
            
            variant_trades.append(sim_trade)
            
        metrics = calculate_metrics(variant_trades)
        result.variants[variant_name] = ResearchVariant(
            name=variant_name,
            config=config_override,
            metrics=metrics,
            trades=variant_trades
        )
        
    result.generate_hash(git_commit=os.getenv("GIT_COMMIT", "HEAD"))
    return result
