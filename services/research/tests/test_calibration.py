import pytest
from datetime import datetime
from shared.types.research import ResearchMetrics, CounterfactualConfig, ResearchVariant, ResearchRunResult
from services.research.calibration import analyze_variant, generate_calibration_report

def test_analyze_variant_high_confidence():
    """HIGH: Expectancy >+0.05R, Drawdown <=0, Volume Retention >= 70%"""
    base = ResearchMetrics(executed_trades=100, expectancy_r=0.5, max_drawdown_r=-2.0, win_rate_pct=50.0)
    var  = ResearchMetrics(executed_trades=80,  expectancy_r=0.6, max_drawdown_r=-1.5, win_rate_pct=52.0)
    
    recco = analyze_variant("var1", var, base)
    assert recco is not None
    assert recco.confidence == "HIGH"
    assert "var1" in recco.proposed_change

def test_analyze_variant_medium_confidence_strict_mode():
    """MEDIUM: Win Rate > +5.0%, Expectancy Flat/Up, Volume significantly dropped (but > 30%)"""
    base = ResearchMetrics(executed_trades=100, expectancy_r=0.5, max_drawdown_r=-2.0, win_rate_pct=50.0)
    var  = ResearchMetrics(executed_trades=40,  expectancy_r=0.52, max_drawdown_r=-1.9, win_rate_pct=56.0)
    
    recco = analyze_variant("strict_var", var, base)
    assert recco is not None
    assert recco.confidence == "MEDIUM"
    assert "strict mode" in recco.title.lower()

def test_analyze_variant_medium_confidence_risk_dampener():
    """MEDIUM: Drawdown drop > 1.0R, Expectancy Flat/Slight down, Retention > 50%"""
    base = ResearchMetrics(executed_trades=100, expectancy_r=0.5, max_drawdown_r=-4.0, win_rate_pct=50.0)
    var  = ResearchMetrics(executed_trades=60,  expectancy_r=0.45, max_drawdown_r=-2.5, win_rate_pct=49.0)
    
    recco = analyze_variant("safe_var", var, base)
    assert recco is not None
    assert recco.confidence == "MEDIUM"
    assert "dampener" in recco.title.lower()

def test_analyze_variant_no_recommendation():
    """Metrics don't hit heuristics."""
    base = ResearchMetrics(executed_trades=100, expectancy_r=0.5, max_drawdown_r=-2.0, win_rate_pct=50.0)
    # Just a little better expectancy but not enough
    var  = ResearchMetrics(executed_trades=90,  expectancy_r=0.52, max_drawdown_r=-2.1, win_rate_pct=51.0)
    
    recco = analyze_variant("meh_var", var, base)
    assert recco is None

def test_generate_calibration_report():
    base = ResearchMetrics(executed_trades=100, expectancy_r=0.5, max_drawdown_r=-2.0, win_rate_pct=50.0)
    high_var = ResearchMetrics(executed_trades=80, expectancy_r=0.6, max_drawdown_r=-1.5, win_rate_pct=52.0)
    meh_var = ResearchMetrics(executed_trades=90, expectancy_r=0.52, max_drawdown_r=-2.1, win_rate_pct=51.0)
    
    cfg = CounterfactualConfig()
    run = ResearchRunResult(
        run_id="run_1",
        pair="XAUUSD",
        start_date=datetime.now(),
        end_date=datetime.now(),
        timeframes=["1m"],
        variants={
            "baseline": ResearchVariant(name="baseline", config=cfg, metrics=base),
            "opt_var": ResearchVariant(name="opt_var", config=cfg, metrics=high_var),
            "meh_var": ResearchVariant(name="meh_var", config=cfg, metrics=meh_var),
        }
    )
    
    report = generate_calibration_report([run], baseline_name="baseline")
    assert report.pair == "XAUUSD"
    assert len(report.recommendations) == 1
    assert report.recommendations[0].confidence == "HIGH"
    
    # Check evidence tables were built
    assert "opt_var" in report.evidence_tables["Metrics"]
    assert "meh_var" in report.evidence_tables["Metrics"]
    assert "baseline" in report.evidence_tables["Metrics"]
    assert report.evidence_tables["Metrics"]["baseline"]["expectancy_r"] == 0.5
