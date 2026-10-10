"""Pay engine: exact, deterministic formulas for trip and weekly mode.

REQUIREMENTS.md sections 5.1 and 5.2. No network calls; no LLM. All inputs
are validated here; negative values are rejected with ValueError.
"""
from typing import List, Optional

from engine.models import (
    CostInputs,
    TripInput,
    TripSummary,
    WeekInput,
    WeeklySummary,
)

_RECONCILIATION_TOLERANCE = 0.5


def _validate_non_negative(value: Optional[float], name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must not be negative (got {value})")


def compute_trip_summary(
    trips: List[TripInput],
    costs: CostInputs,
    logged_in_hours: Optional[float] = None,
    period_days: Optional[int] = None,
) -> TripSummary:
    """Compute trip-mode summary from a list of confirmed trip inputs.

    Returns None for any metric whose denominator is zero or whose required
    data is entirely missing — never returns zero in place of None.
    Rejects negative inputs with ValueError.
    """
    # Validate cost inputs
    _validate_non_negative(costs.fuel_cost_per_km, "fuel_cost_per_km")
    _validate_non_negative(costs.maintenance_cost_per_km, "maintenance_cost_per_km")
    _validate_non_negative(costs.fixed_cost_per_day, "fixed_cost_per_day")
    _validate_non_negative(logged_in_hours, "logged_in_hours")

    data_quality: List[str] = []
    trip_count = len(trips)

    if trip_count == 0:
        return TripSummary(
            gross_pay=None, platform_deductions=None, net_payout=None,
            worker_costs=None, net_earnings=None, engaged_hours=None,
            net_per_engaged_hour=None, net_per_logged_in_hour=None,
            net_payout_per_km=None, deduction_share=None,
            total_distance_km=None, total_duration_min=None,
            trip_count=0, data_quality=["no trips provided"],
        )

    # Validate each trip
    for i, t in enumerate(trips):
        for fname, val in [
            ("base_pay", t.base_pay), ("incentive", t.incentive),
            ("tip", t.tip), ("distance_km", t.distance_km),
            ("duration_min", t.duration_min), ("total_payout", t.total_payout),
        ]:
            _validate_non_negative(val, f"trip[{i}].{fname}")
        for j, d in enumerate(t.deductions):
            if d < 0:
                raise ValueError(f"trip[{i}].deductions[{j}] must not be negative (got {d})")

    # --- gross_pay ---
    # Nulls count as 0 for the sum, but are flagged in data_quality.
    gross_pay = 0.0
    missing_pay_fields = 0
    for t in trips:
        gross_pay += (t.base_pay or 0.0) + (t.incentive or 0.0) + (t.tip or 0.0)
        if t.base_pay is None:
            missing_pay_fields += 1
    if missing_pay_fields > 0:
        data_quality.append(f"{missing_pay_fields} trip(s) have null base_pay — gross_pay may be understated")

    platform_deductions = sum(sum(t.deductions) for t in trips)
    net_payout = gross_pay - platform_deductions

    # --- reconciliation gaps ---
    recon_gaps = []
    for i, t in enumerate(trips):
        if t.total_payout is not None:
            computed = (t.base_pay or 0.0) + (t.incentive or 0.0) + (t.tip or 0.0) - sum(t.deductions)
            gap = computed - t.total_payout
            if abs(gap) > _RECONCILIATION_TOLERANCE:
                recon_gaps.append(i)
    if recon_gaps:
        data_quality.append(f"reconciliation gap > 0.5 on trip(s): {recon_gaps}")

    # --- distance ---
    has_any_distance = any(t.distance_km is not None for t in trips)
    missing_distance_count = sum(1 for t in trips if t.distance_km is None)
    total_distance_km: Optional[float] = None
    if has_any_distance:
        total_distance_km = sum(t.distance_km for t in trips if t.distance_km is not None)
    if missing_distance_count > 0:
        data_quality.append(f"{missing_distance_count} trip(s) have no distance — km-based metrics may be understated")

    # --- duration ---
    has_any_duration = any(t.duration_min is not None for t in trips)
    missing_duration_count = sum(1 for t in trips if t.duration_min is None)
    total_duration_min: Optional[float] = None
    engaged_hours: Optional[float] = None
    if has_any_duration:
        total_duration_min = sum(t.duration_min for t in trips if t.duration_min is not None)
        engaged_hours = total_duration_min / 60.0 if total_duration_min > 0 else None
        if total_duration_min == 0:
            data_quality.append("total engaged time is zero — per-engaged-hour not computed")
    if missing_duration_count > 0:
        data_quality.append(f"{missing_duration_count} trip(s) have no duration — engaged hours may be understated")

    # --- worker costs ---
    cost_per_km = costs.fuel_cost_per_km + costs.maintenance_cost_per_km
    worker_costs: Optional[float] = None
    if total_distance_km is not None:
        worker_costs = total_distance_km * cost_per_km
        if costs.fixed_cost_per_day is not None and period_days is not None and period_days > 0:
            worker_costs += costs.fixed_cost_per_day * period_days
    else:
        data_quality.append("no distance data — worker costs not computed")

    # --- net earnings ---
    net_earnings: Optional[float] = None
    if worker_costs is not None:
        net_earnings = net_payout - worker_costs

    # --- per-hour rates ---
    net_per_engaged_hour: Optional[float] = None
    if net_earnings is not None and engaged_hours is not None and engaged_hours > 0:
        net_per_engaged_hour = net_earnings / engaged_hours

    net_per_logged_in_hour: Optional[float] = None
    if logged_in_hours is not None:
        _validate_non_negative(logged_in_hours, "logged_in_hours")
        if logged_in_hours > 0:
            if net_earnings is not None:
                net_per_logged_in_hour = net_earnings / logged_in_hours
        else:
            data_quality.append("logged_in_hours is zero — per-logged-in-hour not computed")

    # --- per km ---
    net_payout_per_km: Optional[float] = None
    if total_distance_km is not None and total_distance_km > 0:
        net_payout_per_km = net_payout / total_distance_km
    elif total_distance_km == 0:
        data_quality.append("total distance is zero — per-km not computed")

    # --- deduction share ---
    deduction_share: Optional[float] = None
    if gross_pay > 0:
        deduction_share = platform_deductions / gross_pay
    else:
        data_quality.append("gross pay is zero — deduction share not computed")

    return TripSummary(
        gross_pay=round(gross_pay, 2),
        platform_deductions=round(platform_deductions, 2),
        net_payout=round(net_payout, 2),
        worker_costs=round(worker_costs, 2) if worker_costs is not None else None,
        net_earnings=round(net_earnings, 2) if net_earnings is not None else None,
        engaged_hours=round(engaged_hours, 4) if engaged_hours is not None else None,
        net_per_engaged_hour=round(net_per_engaged_hour, 2) if net_per_engaged_hour is not None else None,
        net_per_logged_in_hour=round(net_per_logged_in_hour, 2) if net_per_logged_in_hour is not None else None,
        net_payout_per_km=round(net_payout_per_km, 2) if net_payout_per_km is not None else None,
        deduction_share=round(deduction_share, 4) if deduction_share is not None else None,
        total_distance_km=round(total_distance_km, 4) if total_distance_km is not None else None,
        total_duration_min=round(total_duration_min, 4) if total_duration_min is not None else None,
        trip_count=trip_count,
        data_quality=data_quality,
    )


def compute_weekly_summary(
    week: WeekInput,
    costs: CostInputs,
    period_days: int = 7,
) -> WeeklySummary:
    """Compute weekly-mode summary.

    Returns None for any metric whose denominator is zero or data is missing.
    Rejects negative inputs with ValueError. Per-hour-on-trips is always
    unavailable (no trip minutes in weekly payout screens).
    """
    _validate_non_negative(costs.fuel_cost_per_km, "fuel_cost_per_km")
    _validate_non_negative(costs.maintenance_cost_per_km, "maintenance_cost_per_km")
    _validate_non_negative(costs.fixed_cost_per_day, "fixed_cost_per_day")
    _validate_non_negative(week.km_driven, "km_driven")
    _validate_non_negative(week.hours_online, "hours_online")

    for i, d in enumerate(week.deductions):
        if d < 0:
            raise ValueError(f"deductions[{i}] must not be negative (got {d})")
    for i, line in enumerate(week.lines):
        if line.amount < 0:
            raise ValueError(f"lines[{i}].amount must not be negative (got {line.amount})")

    data_quality: List[str] = []

    gross_weekly = sum(line.amount for line in week.lines)
    deductions_weekly = sum(week.deductions)
    net_payout_weekly = gross_weekly - deductions_weekly

    # --- reconciliation ---
    reconciliation_gap: Optional[float] = None
    if week.total_credited is not None:
        reconciliation_gap = week.total_credited - net_payout_weekly
        if abs(reconciliation_gap) > _RECONCILIATION_TOLERANCE:
            data_quality.append(
                f"reconciliation gap {reconciliation_gap:+.2f} between total_credited and net_payout"
            )

    # --- worker costs ---
    cost_per_km = costs.fuel_cost_per_km + costs.maintenance_cost_per_km
    worker_costs_weekly: Optional[float] = None
    if week.km_driven is not None:
        worker_costs_weekly = week.km_driven * cost_per_km
        if costs.fixed_cost_per_day is not None and period_days > 0:
            worker_costs_weekly += costs.fixed_cost_per_day * period_days
    else:
        data_quality.append("km_driven not provided — worker costs not computed")

    # --- net earnings ---
    net_earnings_weekly: Optional[float] = None
    if worker_costs_weekly is not None:
        net_earnings_weekly = net_payout_weekly - worker_costs_weekly

    # --- per online hour ---
    net_per_online_hour: Optional[float] = None
    if week.hours_online is None:
        data_quality.append("hours_online not provided — per-online-hour not computed")
    elif week.hours_online == 0:
        data_quality.append("hours_online is zero — per-online-hour not computed")
    elif net_earnings_weekly is not None:
        net_per_online_hour = net_earnings_weekly / week.hours_online

    # --- per km ---
    net_payout_per_km: Optional[float] = None
    if week.km_driven is None:
        data_quality.append("km_driven not provided — per-km not computed")
    elif week.km_driven == 0:
        data_quality.append("km_driven is zero — per-km not computed")
    else:
        net_payout_per_km = net_payout_weekly / week.km_driven

    # --- deduction share ---
    deduction_share: Optional[float] = None
    if gross_weekly > 0:
        deduction_share = deductions_weekly / gross_weekly
    else:
        data_quality.append("gross weekly pay is zero — deduction share not computed")

    return WeeklySummary(
        gross_weekly=round(gross_weekly, 2),
        deductions_weekly=round(deductions_weekly, 2),
        net_payout_weekly=round(net_payout_weekly, 2),
        reconciliation_gap=round(reconciliation_gap, 4) if reconciliation_gap is not None else None,
        worker_costs_weekly=round(worker_costs_weekly, 2) if worker_costs_weekly is not None else None,
        net_earnings_weekly=round(net_earnings_weekly, 2) if net_earnings_weekly is not None else None,
        net_per_online_hour=round(net_per_online_hour, 2) if net_per_online_hour is not None else None,
        net_payout_per_km=round(net_payout_per_km, 2) if net_payout_per_km is not None else None,
        deduction_share=round(deduction_share, 4) if deduction_share is not None else None,
        data_quality=data_quality,
    )
