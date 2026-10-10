"""Trip-mode pay-change detection (REQUIREMENTS.md section 5.3).

Seeded bootstrap with 10,000 resamples, 15-trip minimum per period, 5%
relative-change threshold. Weekly-mode change detection is not built
(ROADMAP.md Solo overrides).

The metric compared is net_payout_per_km per trip (net payout for that single
trip divided by its distance). Trips without distance are excluded from this
metric but their exclusion is noted in data_quality.

Hard rule: a trip is only used if date_confirmed is True. Trips with
date_confirmed=False are excluded before any calculation, and their count is
reported in ChangeResult.excluded_unconfirmed.
"""
import random
from typing import List, Optional

from engine.models import ChangeResult, TripInput

_BOOTSTRAP_N = 10_000
_BOOTSTRAP_SEED = 20261006
_MIN_TRIPS = 15
_CHANGE_THRESHOLD = 0.05  # 5% relative change required


def _net_payout_per_km(trip: TripInput) -> Optional[float]:
    """Net payout for one trip / distance. None if distance is missing or zero."""
    if trip.distance_km is None or trip.distance_km <= 0:
        return None
    net = (trip.base_pay or 0.0) + (trip.incentive or 0.0) + (trip.tip or 0.0) - sum(trip.deductions)
    return net / trip.distance_km


def _bootstrap_ci(baseline: List[float], recent: List[float], n: int, seed: int):
    """95% CI of (mean_recent - mean_baseline) via seeded bootstrap resampling."""
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        sample_b = [rng.choice(baseline) for _ in range(len(baseline))]
        sample_r = [rng.choice(recent) for _ in range(len(recent))]
        diffs.append(sum(sample_r) / len(sample_r) - sum(sample_b) / len(sample_b))
    diffs.sort()
    lo = diffs[int(0.025 * n)]
    hi = diffs[int(0.975 * n) - 1]
    return lo, hi


def detect_change(
    baseline_trips: List[TripInput],
    recent_trips: List[TripInput],
    bootstrap_n: int = _BOOTSTRAP_N,
    seed: int = _BOOTSTRAP_SEED,
    min_trips: int = _MIN_TRIPS,
    threshold: float = _CHANGE_THRESHOLD,
) -> ChangeResult:
    """Compare recent trips against a baseline period.

    Returns a ChangeResult with one of three statuses:
    - possible_change: CI excludes 0 AND relative change >= threshold
    - no_clear_change: CI includes 0 OR relative change < threshold
    - insufficient_data: fewer than min_trips in either confirmed period

    Trips with date_confirmed=False are silently excluded before any
    calculation. Their count is reported in excluded_unconfirmed.
    """
    # Filter to date-confirmed trips only
    excluded = sum(1 for t in baseline_trips + recent_trips if not t.date_confirmed)
    baseline_confirmed = [t for t in baseline_trips if t.date_confirmed]
    recent_confirmed = [t for t in recent_trips if t.date_confirmed]

    reason_parts = []
    if excluded > 0:
        reason_parts.append(
            f"{excluded} trip(s) excluded because date_confirmed is false"
        )

    # Extract metric values
    baseline_vals = [v for t in baseline_confirmed if (v := _net_payout_per_km(t)) is not None]
    recent_vals = [v for t in recent_confirmed if (v := _net_payout_per_km(t)) is not None]

    no_km_baseline = len(baseline_confirmed) - len(baseline_vals)
    no_km_recent = len(recent_confirmed) - len(recent_vals)
    if no_km_baseline + no_km_recent > 0:
        reason_parts.append(
            f"{no_km_baseline + no_km_recent} trip(s) excluded from metric due to missing distance"
        )

    if len(baseline_vals) < min_trips or len(recent_vals) < min_trips:
        return ChangeResult(
            status="insufficient_data",
            baseline_count=len(baseline_vals),
            recent_count=len(recent_vals),
            excluded_unconfirmed=excluded,
            reason=(
                f"Need at least {min_trips} trips per period with distance data. "
                f"Got {len(baseline_vals)} baseline, {len(recent_vals)} recent. "
                + " ".join(reason_parts)
            ).strip(),
        )

    baseline_mean = sum(baseline_vals) / len(baseline_vals)
    recent_mean = sum(recent_vals) / len(recent_vals)

    if baseline_mean == 0:
        return ChangeResult(
            status="insufficient_data",
            baseline_count=len(baseline_vals),
            recent_count=len(recent_vals),
            excluded_unconfirmed=excluded,
            reason="Baseline mean is zero — relative change cannot be computed.",
        )

    relative_change = (recent_mean - baseline_mean) / abs(baseline_mean)
    ci_low, ci_high = _bootstrap_ci(baseline_vals, recent_vals, bootstrap_n, seed)

    ci_excludes_zero = ci_high < 0 or ci_low > 0
    change_large_enough = abs(relative_change) >= threshold

    if ci_excludes_zero and change_large_enough:
        status = "possible_change"
    else:
        status = "no_clear_change"

    return ChangeResult(
        status=status,
        metric="net_payout_per_km",
        baseline_mean=round(baseline_mean, 4),
        recent_mean=round(recent_mean, 4),
        relative_change=round(relative_change, 4),
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        baseline_count=len(baseline_vals),
        recent_count=len(recent_vals),
        excluded_unconfirmed=excluded,
        reason=" ".join(reason_parts) if reason_parts else None,
    )
