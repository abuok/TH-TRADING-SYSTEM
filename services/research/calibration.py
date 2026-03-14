import json
import uuid
from datetime import datetime
from typing import Any

import pytz

from shared.types.calibration import CalibrationReport, Recommendation
from shared.types.research import ResearchMetrics, ResearchRunResult
from shared.utils.metadata import get_system_metadata

NAIROBI = pytz.timezone("Africa/Nairobi")


def analyze_variant(
    variant_name: str,
    variant_metrics: ResearchMetrics,
    baseline_metrics: ResearchMetrics,
    min_volume_retention: float = 0.70,
) -> Recommendation | None:
    """
    Compares a variant's metrics against the baseline and returns a Recommendation
    if the variant provides a statistically meaningful improvement according to heuristics.
    """
    if baseline_metrics.executed_trades == 0:
        return None  # Cannot compare against an empty baseline

    retention = variant_metrics.executed_trades / baseline_metrics.executed_trades

    # Calculate Deltas
    er_delta = variant_metrics.expectancy_r - baseline_metrics.expectancy_r
    dd_delta = (
        baseline_metrics.max_drawdown_r - variant_metrics.max_drawdown_r
    )  # Positive means DD decreased (improved)
    win_rate_delta = variant_metrics.win_rate_pct - baseline_metrics.win_rate_pct

    recco_id = f"rec_{uuid.uuid4().hex[:6]}"

    # 1. High Conviction: Expectancy UP, Drawdown UP (towards 0), Volume Stable
    if er_delta > 0.05 and dd_delta >= 0.0 and retention >= min_volume_retention:
        return Recommendation(
            id=recco_id,
            title=f"Adopt {variant_name} settings",
            change_type="threshold",
            proposed_change=f"Apply configuration from variant '{variant_name}'",
            expected_impact=f"Improves expectancy by +{er_delta:.2f}R and reduces drawdown by {dd_delta:.2f}R, while retaining {retention * 100:.0f}% of trades.",
            conviction="HIGH",
            rationale="Clear improvement in risk-adjusted returns without collapsing signal volume.",
            caveats="Ensure the historical window used is representative of current market regimes.",
        )

    # 2. Medium Conviction: Win Rate UP, Expectancy Flat/Slight UP, Volume Significant Drop
    if (
        win_rate_delta > 5.0
        and er_delta >= -0.05
        and retention < min_volume_retention
        and retention > 0.3
    ):
        return Recommendation(
            id=recco_id,
            title=f"Consider {variant_name} for strict mode",
            change_type="hard_block",
            proposed_change=f"Enable strict rules from '{variant_name}' during low conviction regimes.",
            expected_impact=f"Boosts win rate by +{win_rate_delta:.1f}% but cuts trading volume significantly (retains {retention * 100:.0f}%).",
            conviction="MEDIUM",
            rationale="Sacrifices opportunity for extreme precision. Suitable for ranging or choppy markets.",
            caveats=f"Severe volume reduction ({100 - retention * 100:.0f}% drop) may cause plateau periods.",
        )

    # 3. Medium Conviction: Drawdown Significantly UP (towards 0), Expectancy Flat/Slight DOWN
    if dd_delta > 1.0 and er_delta >= -0.1 and retention >= 0.5:
        return Recommendation(
            id=recco_id,
            title=f"Risk dampener via {variant_name}",
            change_type="threshold",
            proposed_change=f"Configure '{variant_name}' logic to arrest drawdowns.",
            expected_impact=f"Saves {dd_delta:.1f}R in max drawdown at a slight cost to expectancy ({er_delta:.2f}R).",
            conviction="MEDIUM",
            rationale="Capital preservation strategy optimized for limiting tail-risk strings of losses.",
            caveats="Will filter out some winning trades.",
        )

    return None


def generate_calibration_report(
    run_results: list[ResearchRunResult],
    baseline_name: str = "baseline",
    min_volume_retention: float = 0.70,
) -> CalibrationReport:
    """
    Ingest baseline + variants results, compute deltas across key metrics,
    and generate a CalibrationReport containing the most viable policy changes.
    """

    # We assume all run_results belong to the same pair and rough date range for a single report.
    if not run_results:
        raise ValueError("Must provide at least one ResearchRunResult to calibrate.")

    base_run = run_results[0]
    pair = base_run.pair
    timeframes = base_run.timeframes
    start_date = min(r.start_date for r in run_results).strftime("%Y-%m-%d")
    end_date = max(r.end_date for r in run_results).strftime("%Y-%m-%d")

    report_id = f"cal_{uuid.uuid4().hex[:8]}"

    # Find baseline metrics
    baseline_metrics = None
    baseline_hash = "unknown"
    for r in run_results:
        if baseline_name in r.variants:
            baseline_metrics = r.variants[baseline_name].metrics
            baseline_hash = str(
                hash(
                    json.dumps(
                        r.variants[baseline_name].config.model_dump(mode="json"),
                        sort_keys=True,
                    )
                )
            )
            break

    if not baseline_metrics:
        raise ValueError(
            f"Baseline variant '{baseline_name}' not found in any of the provided run results."
        )

    recommendations: list[Recommendation] = []
    evidence_tables: dict[str, Any] = {
        "Metrics": {baseline_name: baseline_metrics.model_dump()}
    }

    # Compare all variants
    for run in run_results:
        for var_name, variant in run.variants.items():
            if var_name == baseline_name:
                continue

            evidence_tables["Metrics"][var_name] = variant.metrics.model_dump()

            recco = analyze_variant(
                variant_name=var_name,
                variant_metrics=variant.metrics,
                baseline_metrics=baseline_metrics,
                min_volume_retention=min_volume_retention,
            )

            if recco:
                recommendations.append(recco)

    # Sort recommendations by conviction
    conv_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recommendations.sort(key=lambda x: conv_rank.get(x.conviction, 99))

    return CalibrationReport(
        report_id=report_id,
        created_at=datetime.now(NAIROBI),
        run_ids=[r.run_id for r in run_results],
        pair=pair,
        timeframe=",".join(timeframes),
        date_range=f"{start_date} to {end_date}",
        baseline_policy_hash=baseline_hash,
        recommendations=recommendations,
        evidence_tables=evidence_tables,
        reproducibility=get_system_metadata(),
    )
