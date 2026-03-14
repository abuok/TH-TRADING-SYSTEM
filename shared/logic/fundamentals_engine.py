"""
shared/logic/fundamentals_engine.py
Deterministic scoring engine for generating bias logic based on proxy snapshots and events.
No external calls, explainable mapping to specific rules for XAUUSD and GBPJPY.
"""

import logging
from datetime import datetime

from shared.types.fundamentals import (
    BulletItem,
    MarketMoversPacket,
    PairFundamentalsPacket,
    ProxySnapshot,
)

logger = logging.getLogger("FundamentalsEngine")


def _determine_label(score: float) -> str:
    if score >= 2.0:
        return "BULLISH"
    elif score <= -2.0:
        return "BEARISH"
    return "NEUTRAL"


# ── XAUUSD (Gold) Logic ──────────────────────────────────────────────────
# Rules:
# DXY Up -> Bearish XAU
# Yields (US10Y) Up -> Bearish XAU
# Risk Off (SPX Down) -> Bullish XAU


def evaluate_xauusd(
    proxies: dict[str, ProxySnapshot], events: list[dict], created_at: datetime
) -> PairFundamentalsPacket:
    score = 0.0
    drivers = []

    # 1. DXY (US Dollar Index)
    dxy = proxies.get("DXY")
    if dxy and dxy.delta_pct is not None:
        if dxy.delta_pct > 0.1:
            score -= 2.0
            drivers.append(
                BulletItem(
                    category="USD",
                    text=f"DXY Rising (+{dxy.delta_pct:.2f}%)",
                    impact=-1,
                )
            )
        elif dxy.delta_pct < -0.1:
            score += 2.0
            drivers.append(
                BulletItem(
                    category="USD", text=f"DXY Falling ({dxy.delta_pct:.2f}%)", impact=1
                )
            )
        else:
            drivers.append(
                BulletItem(
                    category="USD", text=f"DXY Flat ({dxy.delta_pct:.2f}%)", impact=0
                )
            )

    # 2. US10Y (US 10-Year Yields)
    us10y = proxies.get("US10Y")
    if us10y and us10y.delta_pct is not None:
        if (
            us10y.delta_pct > 1.0
        ):  # Yields move differently, using 1% delta for significance
            score -= 2.0
            drivers.append(
                BulletItem(
                    category="YIELDS",
                    text=f"US10Y Rising (+{us10y.delta_pct:.2f}%)",
                    impact=-1,
                )
            )
        elif us10y.delta_pct < -1.0:
            score += 2.0
            drivers.append(
                BulletItem(
                    category="YIELDS",
                    text=f"US10Y Falling ({us10y.delta_pct:.2f}%)",
                    impact=1,
                )
            )
        else:
            drivers.append(
                BulletItem(
                    category="YIELDS",
                    text=f"US10Y Flat ({us10y.delta_pct:.2f}%)",
                    impact=0,
                )
            )

    # 3. SPX (Risk Sentiment) - Gold is a safe haven
    spx = proxies.get("SPX")
    if spx and spx.delta_pct is not None:
        if spx.delta_pct < -0.5:
            score += 1.0  # Risk off -> Bullish Gold
            drivers.append(
                BulletItem(
                    category="RISK_SENTIMENT",
                    text=f"Risk-Off: SPX drop ({spx.delta_pct:.2f}%)",
                    impact=1,
                )
            )
        elif spx.delta_pct > 0.5:
            score -= 1.0  # Risk on -> Bearish Gold (opportunity cost)
            drivers.append(
                BulletItem(
                    category="RISK_SENTIMENT",
                    text=f"Risk-On: SPX rally (+{spx.delta_pct:.2f}%)",
                    impact=-1,
                )
            )

    # Cap score between -5 and 5
    score = max(-5.0, min(5.0, score))

    label = _determine_label(score)

    invalidation = "Neutral proxy movement or sharp DXY reversal"
    if label == "BULLISH":
        invalidation = "DXY strongly rising or US10Y breakout"
    elif label == "BEARISH":
        invalidation = "Collapse in DXY/Yields or sudden risk-off event"

    return PairFundamentalsPacket(
        asset_pair="XAUUSD",
        created_at=created_at,
        bias_score=score,
        bias_label=label,
        drivers=drivers,
        invalidation_criteria=invalidation,
        sources=["DeterministicModel_V1", "ProxyDeltas"],
    )


# ── GBPJPY Logic ─────────────────────────────────────────────────────────
# Rules:
# SPX Up (Risk On) -> JPY weakens -> Bullish GBPJPY
# BoJ Hawkish / UK Dovish -> Bearish GBPJPY (via event keywords)


def evaluate_gbpjpy(
    proxies: dict[str, ProxySnapshot], events: list[dict], created_at: datetime
) -> PairFundamentalsPacket:
    score = 0.0
    drivers = []

    # 1. Broad Risk Sentiment (SPX)
    spx = proxies.get("SPX")
    if spx and spx.delta_pct is not None:
        if spx.delta_pct > 0.5:
            score += 2.0  # Risk On -> JPY weakness -> GBPJPY rises
            drivers.append(
                BulletItem(
                    category="RISK_SENTIMENT",
                    text=f"Risk-On: SPX Rally (+{spx.delta_pct:.2f}%)",
                    impact=1,
                )
            )
        elif spx.delta_pct < -0.5:
            score -= 2.0  # Risk Off -> JPY strength -> GBPJPY drops
            drivers.append(
                BulletItem(
                    category="RISK_SENTIMENT",
                    text=f"Risk-Off: SPX Drop ({spx.delta_pct:.2f}%)",
                    impact=-1,
                )
            )
        else:
            drivers.append(
                BulletItem(
                    category="RISK_SENTIMENT", text="Neutral Risk Sentiment", impact=0
                )
            )

    # 2. Central Bank divergence via events
    boj_keywords = ["boj", "bank of japan", "ueda", "ycc", "nirp"]
    boe_keywords = ["boe", "bank of england", "bailey", "mpc", "bank rate"]

    boj_hawkish = any(
        any(kw in e.get("event", "").lower() for kw in boj_keywords)
        and any(
            kw in e.get("event", "").lower()
            for kw in ["rate", "hike", "hawkish", "tighten"]
        )
        for e in events
    )

    boe_hawkish = any(
        any(kw in e.get("event", "").lower() for kw in boe_keywords)
        and any(
            kw in e.get("event", "").lower()
            for kw in ["rate", "hike", "hawkish", "tighten"]
        )
        for e in events
    )

    if boj_hawkish:
        score -= 2.0
        drivers.append(
            BulletItem(
                category="CENTRAL_BANKS",
                text="BoJ Policy Event (JPY Strength Risk)",
                impact=-1,
            )
        )
    if boe_hawkish:
        score += 2.0
        drivers.append(
            BulletItem(
                category="CENTRAL_BANKS",
                text="BoE Policy Event (GBP Strength Risk)",
                impact=1,
            )
        )

    score = max(-5.0, min(5.0, score))
    label = _determine_label(score)

    invalidation = "Shift in broad risk sentiment (SPX reversal)"
    if label == "BULLISH":
        invalidation = "Sudden risk-off event driving JPY haven flow"
    elif label == "BEARISH":
        invalidation = "Risk-on rally or dovish BoJ surprise"

    return PairFundamentalsPacket(
        asset_pair="GBPJPY",
        created_at=created_at,
        bias_score=score,
        bias_label=label,
        drivers=drivers,
        invalidation_criteria=invalidation,
        sources=["DeterministicModel_V1", "ProxyDeltas"],
    )


def evaluate_fundamentals(
    context_packet_data: dict, created_at: datetime
) -> tuple[MarketMoversPacket, list[PairFundamentalsPacket]]:
    """
    Given an ingestion context packet (with populated proxies and events),
    run the deterministic engines. We assume proxies in context_packet_data
    are already formatted as ProxySnapshots or dicts.
    """
    raw_proxies = context_packet_data.get("proxies", {})
    events = context_packet_data.get("high_impact_events", [])

    # Translate raw dicts to ProxySnapshots
    proxies: dict[str, ProxySnapshot] = {}
    for sym, pd in raw_proxies.items():
        if isinstance(pd, dict):
            proxies[sym] = ProxySnapshot(**pd)
        elif isinstance(pd, float):
            # Fallback if no delta is provided, construct a naive snapshot
            proxies[sym] = ProxySnapshot(symbol=sym, current_value=pd)

    # Build global MarketMovers
    # Determine sentiment flag broadly
    flags = []
    if "SPX" in proxies and proxies["SPX"].delta_pct is not None:
        if proxies["SPX"].delta_pct < -1.0:
            flags.append("RISK_OFF")
        elif proxies["SPX"].delta_pct > 1.0:
            flags.append("RISK_ON")

    movers = MarketMoversPacket(
        created_at=created_at,
        proxies=proxies,
        sentiment_flags=flags,
        sources=["Ingest Context Sync"],
    )

    # Build pair fundamentals
    pair_packets = [
        evaluate_xauusd(proxies, events, created_at),
        evaluate_gbpjpy(proxies, events, created_at),
    ]

    return movers, pair_packets
