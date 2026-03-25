from datetime import datetime

from shared.logic.fundamentals_engine import (
    evaluate_fundamentals,
    evaluate_gbpjpy,
    evaluate_xauusd,
)
from shared.types.fundamentals import ProxySnapshot


def test_xauusd_bearish_on_rising_dxy_and_yields():
    proxies = {
        "DXY": ProxySnapshot(
            symbol="DXY", current_value=105.0, previous_value=104.0, delta_pct=0.96
        ),
        "US10Y": ProxySnapshot(
            symbol="US10Y", current_value=4.5, previous_value=4.1, delta_pct=1.2
        ),
    }

    packet = evaluate_xauusd(proxies, [], datetime.now())

    assert packet.bias_label == "BEARISH"
    assert packet.bias_score <= -4.0  # -2 from DXY, -2 from US10Y
    assert "DXY" in packet.drivers[0].text


def test_xauusd_bullish_on_risk_off():
    proxies = {
        "SPX": ProxySnapshot(
            symbol="SPX", current_value=4800.0, previous_value=5000.0, delta_pct=-4.0
        )
    }

    packet = evaluate_xauusd(proxies, [], datetime.now())

    assert (
        packet.bias_label == "NEUTRAL" or packet.bias_label == "BULLISH"
    )  # Only +1 from risk-off, so might be neutral but score is positive
    assert packet.bias_score == 1.0


def test_gbpjpy_bullish_on_risk_on():
    proxies = {
        "SPX": ProxySnapshot(
            symbol="SPX", current_value=5100.0, previous_value=5000.0, delta_pct=2.0
        )
    }

    packet = evaluate_gbpjpy(proxies, [], datetime.now())

    assert packet.bias_label == "BULLISH"
    assert packet.bias_score == 2.0
    assert "Risk-On" in packet.drivers[0].text


def test_gbpjpy_bearish_on_boj_hawkishness():
    # SPX flat, BoJ hawkish
    proxies = {
        "SPX": ProxySnapshot(
            symbol="SPX", current_value=5000.0, previous_value=5000.0, delta_pct=0.0
        )
    }
    events = [{"event": "BoJ Interest Rate Decision", "impact": "High"}]

    packet = evaluate_gbpjpy(proxies, events, datetime.now())

    assert packet.bias_label == "BEARISH"
    assert packet.bias_score == -2.0
    assert "BoJ" in packet.drivers[1].text  # drivers[0] is neutral SPX


def test_evaluate_fundamentals_full_context():
    # Context dictionary exactly as produced by ingestion
    ctx = {
        "proxies": {
            "DXY": {"symbol": "DXY", "current_value": 105.0, "delta_pct": 0.5},
            "US10Y": {"symbol": "US10Y", "current_value": 4.5, "delta_pct": 1.5},
            "SPX": {
                "symbol": "SPX",
                "current_value": 4900.0,
                "delta_pct": -2.0,
            },  # Risk Off
        },
        "high_impact_events": [{"event": "BoE Interest Rate Hike Decision"}],
    }

    movers, pair_packets = evaluate_fundamentals(ctx, datetime.now())
    pair_packets: list[PairFundamentalsPacket] = pair_packets

    assert movers.packet_type == "MarketMoversPacket"
    assert "RISK_OFF" in movers.sentiment_flags

    assert len(pair_packets) == 2
    xau = next(p for p in pair_packets if p.asset_pair == "XAUUSD")
    gbp = next(p for p in pair_packets if p.asset_pair == "GBPJPY")

    assert xau.bias_score == -3.0  # -2 (DXY) -2 (US10Y) +1 (Risk Off)
    assert xau.bias_label == "BEARISH"

    assert gbp.bias_score == 0.0  # -2 (Risk Off SPX drop) +2 (BoE hawkish keywords)
    assert gbp.bias_label == "NEUTRAL"
