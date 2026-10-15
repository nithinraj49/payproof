"""Input and output models for the pay engine (REQUIREMENTS.md section 5).

Pure Python dataclasses; no network calls; no LLM. All arithmetic lives in
engine/earnings.py. These models are intentionally separate from the extraction
schema so the engine never has a hard dependency on the Gemini pipeline.
"""
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

@dataclass
class CostInputs:
    fuel_cost_per_km: float
    maintenance_cost_per_km: float
    fixed_cost_per_day: Optional[float] = None


# ---------------------------------------------------------------------------
# Trip mode
# ---------------------------------------------------------------------------

@dataclass
class TripInput:
    """One confirmed trip row as stored by backend/store.py.

    date_confirmed must be True before the engine uses trip_date for any
    period-boundary comparison (FE-3, REQUIREMENTS.md section 5.3).
    """
    base_pay: Optional[float] = None
    incentive: Optional[float] = None
    tip: Optional[float] = None
    deductions: List[float] = field(default_factory=list)
    total_payout: Optional[float] = None
    distance_km: Optional[float] = None
    duration_min: Optional[float] = None
    trip_date: Optional[str] = None
    date_confirmed: bool = False


@dataclass
class TripReconciliation:
    """One trip whose parts do not add up to its screenshot's total payout."""
    trip_index: int
    computed_total: float
    total_payout: float
    gap: float


@dataclass
class TripSummary:
    gross_pay: Optional[float]
    platform_deductions: Optional[float]
    net_payout: Optional[float]
    worker_costs: Optional[float]
    net_earnings: Optional[float]
    engaged_hours: Optional[float]
    net_per_engaged_hour: Optional[float]
    net_per_logged_in_hour: Optional[float]
    net_payout_per_km: Optional[float]
    deduction_share: Optional[float]
    total_distance_km: Optional[float]
    total_duration_min: Optional[float]
    trip_count: int
    data_quality: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Weekly mode
# ---------------------------------------------------------------------------

@dataclass
class PayoutLine:
    label: str
    amount: float


@dataclass
class WeekInput:
    lines: List[PayoutLine]
    deductions: List[float] = field(default_factory=list)
    total_credited: Optional[float] = None
    km_driven: Optional[float] = None
    hours_online: Optional[float] = None


@dataclass
class WeeklySummary:
    gross_weekly: Optional[float]
    deductions_weekly: Optional[float]
    net_payout_weekly: Optional[float]
    reconciliation_gap: Optional[float]
    worker_costs_weekly: Optional[float]
    net_earnings_weekly: Optional[float]
    net_per_online_hour: Optional[float]
    net_payout_per_km: Optional[float]
    deduction_share: Optional[float]
    # Per-hour-on-trips is structurally unavailable in weekly mode (no trip
    # minutes). The UI must show this reason, not a blank (FE-7).
    per_hour_on_trips_unavailable: str = "not available in weekly mode — no per-trip minutes"
    data_quality: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Change detection (trip mode only, engine/changes.py)
# ---------------------------------------------------------------------------

@dataclass
class ChangeResult:
    status: str  # possible_change | no_clear_change | insufficient_data
    metric: Optional[str] = None
    baseline_mean: Optional[float] = None
    recent_mean: Optional[float] = None
    relative_change: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    baseline_count: Optional[int] = None
    recent_count: Optional[int] = None
    reason: Optional[str] = None
    excluded_unconfirmed: int = 0
