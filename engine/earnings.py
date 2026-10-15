"""Pay engine: exact, deterministic formulas for trip and weekly mode.

REQUIREMENTS.md sections 5.1 and 5.2. No network calls; no LLM. All inputs
are validated here; negative values are rejected with ValueError.

Money arithmetic is done in Decimal (built from each float's shortest
repr, so 136.65 is exactly 136.65) and rounded for output with
ROUND_HALF_UP, so an exact half such as 7823 / 40 = 195.575 shows as
195.58, not the 195.57 that binary floats and Python's round() give.
The deduction share keeps 4 decimals.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from engine.models import (
    CostInputs,
    TripInput,
    TripReconciliation,
    TripSummary,
    WeekInput,
    WeeklySummary,
)

_RECONCILIATION_TOLERANCE = 0.5
_TOLERANCE_D = Decimal("0.5")
_ZERO = Decimal(0)


def _d(value) -> Decimal:
    return Decimal(str(value))


def _q(value: Decimal, places: int) -> float:
    """Round half up to `places` decimals and return a float."""
    return float(value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def _inr(value: Decimal) -> str:
    """₹ with Indian digit grouping (1,23,456.78), for user-facing notes."""
    amount = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    integer, _, decimals = f"{abs(amount):.2f}".partition(".")
    if len(integer) > 3:
        head, tail = integer[:-3], integer[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        integer = ",".join(groups) + "," + tail
    return f"{sign}₹{integer}.{decimals}"


def _trips(n: int) -> str:
    return "1 trip has" if n == 1 else f"{n} trips have"


def _validate_non_negative(value: Optional[float], name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must not be negative (got {value})")


def _trip_total(t: TripInput) -> Decimal:
    """base pay + incentive + tip - deductions (missing parts count as 0)."""
    parts = _d(t.base_pay or 0) + _d(t.incentive or 0) + _d(t.tip or 0)
    return parts - sum((_d(x) for x in t.deductions), _ZERO)


def reconcile_trips(trips: List[TripInput]) -> List[TripReconciliation]:
    """Trips where base pay + incentive + tip - deductions differs from the
    screenshot's total payout by more than the tolerance (0.5).

    A trip with no total_payout cannot be checked and is never flagged.
    Missing parts count as 0, the same as compute_trip_summary.
    """
    flagged: List[TripReconciliation] = []
    for i, t in enumerate(trips):
        if t.total_payout is None:
            continue
        for name, val in [("base_pay", t.base_pay), ("incentive", t.incentive),
                          ("tip", t.tip), ("total_payout", t.total_payout)]:
            _validate_non_negative(val, f"trip[{i}].{name}")
        if any(d < 0 for d in t.deductions):
            raise ValueError(f"trip[{i}].deductions must not be negative")
        computed = _trip_total(t)
        gap = computed - _d(t.total_payout)
        if abs(gap) > _TOLERANCE_D:
            flagged.append(TripReconciliation(
                trip_index=i,
                computed_total=_q(computed, 2),
                total_payout=_q(_d(t.total_payout), 2),
                gap=_q(gap, 2),
            ))
    return flagged


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
            trip_count=0, data_quality=["No trips were provided."],
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
    gross_pay = _ZERO
    missing_pay_fields = 0
    for t in trips:
        gross_pay += _d(t.base_pay or 0) + _d(t.incentive or 0) + _d(t.tip or 0)
        if t.base_pay is None:
            missing_pay_fields += 1
    if missing_pay_fields > 0:
        data_quality.append(f"{_trips(missing_pay_fields)} no base pay, so gross pay may be understated.")

    platform_deductions = sum((_d(x) for t in trips for x in t.deductions), _ZERO)
    net_payout = gross_pay - platform_deductions

    # --- reconciliation gaps (human numbering, engine amounts) ---
    for r in reconcile_trips(trips):
        data_quality.append(
            f"Trip {r.trip_index + 1}: the amounts add up to {_inr(_d(r.computed_total))}, "
            f"but its screenshot says {_inr(_d(r.total_payout))}."
        )

    # --- distance ---
    has_any_distance = any(t.distance_km is not None for t in trips)
    missing_distance_count = sum(1 for t in trips if t.distance_km is None)
    total_distance_km: Optional[Decimal] = None
    if has_any_distance:
        total_distance_km = sum((_d(t.distance_km) for t in trips if t.distance_km is not None), _ZERO)
    if missing_distance_count > 0:
        data_quality.append(
            f"{_trips(missing_distance_count)} no distance, so pay per km and your costs may be off."
        )

    # --- duration ---
    has_any_duration = any(t.duration_min is not None for t in trips)
    missing_duration_count = sum(1 for t in trips if t.duration_min is None)
    total_duration_min: Optional[Decimal] = None
    engaged_hours: Optional[Decimal] = None
    if has_any_duration:
        total_duration_min = sum((_d(t.duration_min) for t in trips if t.duration_min is not None), _ZERO)
        engaged_hours = total_duration_min / Decimal(60) if total_duration_min > 0 else None
        if total_duration_min == 0:
            data_quality.append("Total time on trips is zero, so pay per hour on trips is not shown.")
    if missing_duration_count > 0:
        data_quality.append(
            f"{_trips(missing_duration_count)} no duration, so hours on trips may be understated."
        )

    # --- worker costs ---
    cost_per_km = _d(costs.fuel_cost_per_km) + _d(costs.maintenance_cost_per_km)
    worker_costs: Optional[Decimal] = None
    if total_distance_km is not None:
        worker_costs = total_distance_km * cost_per_km
        if costs.fixed_cost_per_day is not None and period_days is not None and period_days > 0:
            worker_costs += _d(costs.fixed_cost_per_day) * period_days
    else:
        data_quality.append("None of your trips has a distance, so your costs and net earnings cannot be worked out.")

    # --- net earnings ---
    net_earnings: Optional[Decimal] = None
    if worker_costs is not None:
        net_earnings = net_payout - worker_costs

    # --- per-hour rates ---
    net_per_engaged_hour: Optional[Decimal] = None
    if net_earnings is not None and total_duration_min is not None and total_duration_min > 0:
        net_per_engaged_hour = net_earnings * Decimal(60) / total_duration_min

    net_per_logged_in_hour: Optional[Decimal] = None
    if logged_in_hours is not None:
        _validate_non_negative(logged_in_hours, "logged_in_hours")
        if logged_in_hours > 0:
            if net_earnings is not None:
                net_per_logged_in_hour = net_earnings / _d(logged_in_hours)
        else:
            data_quality.append("Hours online is zero, so pay per hour online is not shown.")

    # --- per km ---
    net_payout_per_km: Optional[Decimal] = None
    if total_distance_km is not None and total_distance_km > 0:
        net_payout_per_km = net_payout / total_distance_km
    elif total_distance_km == 0:
        data_quality.append("Total distance is zero, so pay per km is not shown.")

    # --- deduction share ---
    deduction_share: Optional[Decimal] = None
    if gross_pay > 0:
        deduction_share = platform_deductions / gross_pay
    else:
        data_quality.append("Gross pay is zero, so the deduction share is not shown.")

    def q2(v: Optional[Decimal]) -> Optional[float]:
        return _q(v, 2) if v is not None else None

    return TripSummary(
        gross_pay=_q(gross_pay, 2),
        platform_deductions=_q(platform_deductions, 2),
        net_payout=_q(net_payout, 2),
        worker_costs=q2(worker_costs),
        net_earnings=q2(net_earnings),
        engaged_hours=_q(engaged_hours, 4) if engaged_hours is not None else None,
        net_per_engaged_hour=q2(net_per_engaged_hour),
        net_per_logged_in_hour=q2(net_per_logged_in_hour),
        net_payout_per_km=q2(net_payout_per_km),
        deduction_share=_q(deduction_share, 4) if deduction_share is not None else None,
        total_distance_km=_q(total_distance_km, 4) if total_distance_km is not None else None,
        total_duration_min=_q(total_duration_min, 4) if total_duration_min is not None else None,
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

    gross_weekly = sum((_d(line.amount) for line in week.lines), _ZERO)
    deductions_weekly = sum((_d(x) for x in week.deductions), _ZERO)
    net_payout_weekly = gross_weekly - deductions_weekly

    # --- reconciliation ---
    reconciliation_gap: Optional[Decimal] = None
    if week.total_credited is not None:
        reconciliation_gap = _d(week.total_credited) - net_payout_weekly
        if abs(reconciliation_gap) > _TOLERANCE_D:
            data_quality.append(
                f"The earning lines add up to {_inr(net_payout_weekly)}, but your screenshot says "
                f"{_inr(_d(week.total_credited))} was credited."
            )

    # --- worker costs ---
    cost_per_km = _d(costs.fuel_cost_per_km) + _d(costs.maintenance_cost_per_km)
    worker_costs_weekly: Optional[Decimal] = None
    if week.km_driven is not None:
        worker_costs_weekly = _d(week.km_driven) * cost_per_km
        if costs.fixed_cost_per_day is not None and period_days > 0:
            worker_costs_weekly += _d(costs.fixed_cost_per_day) * period_days
    else:
        data_quality.append("Distance driven was not provided, so your costs and net earnings are not shown.")

    # --- net earnings ---
    net_earnings_weekly: Optional[Decimal] = None
    if worker_costs_weekly is not None:
        net_earnings_weekly = net_payout_weekly - worker_costs_weekly

    # --- per online hour ---
    net_per_online_hour: Optional[Decimal] = None
    if week.hours_online is None:
        data_quality.append("Hours online was not provided, so pay per hour online is not shown.")
    elif week.hours_online == 0:
        data_quality.append("Hours online is zero, so pay per hour online is not shown.")
    elif net_earnings_weekly is not None:
        net_per_online_hour = net_earnings_weekly / _d(week.hours_online)

    # --- per km ---
    net_payout_per_km: Optional[Decimal] = None
    if week.km_driven is None:
        data_quality.append("Distance driven was not provided, so pay per km is not shown.")
    elif week.km_driven == 0:
        data_quality.append("Distance driven is zero, so pay per km is not shown.")
    else:
        net_payout_per_km = net_payout_weekly / _d(week.km_driven)

    # --- deduction share ---
    deduction_share: Optional[Decimal] = None
    if gross_weekly > 0:
        deduction_share = deductions_weekly / gross_weekly
    else:
        data_quality.append("Gross weekly pay is zero, so the deduction share is not shown.")

    def q2(v: Optional[Decimal]) -> Optional[float]:
        return _q(v, 2) if v is not None else None

    return WeeklySummary(
        gross_weekly=_q(gross_weekly, 2),
        deductions_weekly=_q(deductions_weekly, 2),
        net_payout_weekly=_q(net_payout_weekly, 2),
        reconciliation_gap=_q(reconciliation_gap, 4) if reconciliation_gap is not None else None,
        worker_costs_weekly=q2(worker_costs_weekly),
        net_earnings_weekly=q2(net_earnings_weekly),
        net_per_online_hour=q2(net_per_online_hour),
        net_payout_per_km=q2(net_payout_per_km),
        deduction_share=_q(deduction_share, 4) if deduction_share is not None else None,
        data_quality=data_quality,
    )
