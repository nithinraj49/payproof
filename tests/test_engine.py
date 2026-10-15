"""Engine tests: both worked examples from REQUIREMENTS.md sections 5.1 and 5.2,
plus at least 8 hand-computed additional cases per mode. No network calls.

Hand calculations appear in comments above each test.
"""
import pytest

from engine.changes import detect_change
from engine.earnings import compute_trip_summary, compute_weekly_summary
from engine.models import CostInputs, PayoutLine, TripInput, WeekInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def trips(*args) -> list:
    return list(args)


def t(base=None, inc=None, tip=None, deds=None, total=None, km=None, mins=None, date=None, confirmed=True):
    return TripInput(
        base_pay=base, incentive=inc, tip=tip,
        deductions=deds or [], total_payout=total,
        distance_km=km, duration_min=mins,
        trip_date=date, date_confirmed=confirmed,
    )


def costs(fuel=3.0, maint=1.0, fixed=None):
    return CostInputs(fuel_cost_per_km=fuel, maintenance_cost_per_km=maint, fixed_cost_per_day=fixed)


def week(lines_kv, deds=None, credited=None, km=None, hours=None):
    lines = [PayoutLine(label=k, amount=v) for k, v in lines_kv.items()]
    return WeekInput(lines=lines, deductions=deds or [], total_credited=credited,
                     km_driven=km, hours_online=hours)


# ===========================================================================
# TRIP MODE
# ===========================================================================

class TestTripWorkedExample:
    """REQUIREMENTS.md section 5.1 worked example.

    Trip 1: base 80, incentive 20, tip 10, fee 10, 5 km, 25 min
    Trip 2: base 60, no incentive/tip/deductions, 3 km, 15 min
    Costs: fuel 3.0, maintenance 1.0 per km.  Logged-in hours: 1.5

    gross = (80+20+10) + (60+0+0)     = 110 + 60 = 170
    platform_deductions = 10 (trip 1 fee) + 0 = 10
    net_payout = 170 - 10 = 160
    total_distance = 5 + 3 = 8 km
    worker_costs = 8 * (3.0+1.0) = 8 * 4 = 32
    net_earnings = 160 - 32 = 128
    engaged_hours = (25+15)/60 = 40/60 ≈ 0.6667
    per_engaged_hour = 128 / (40/60) = 128 * 60/40 = 192.00
    per_logged_in_hour = 128 / 1.5 = 85.3333 → 85.33
    per_km = 160 / 8 = 20.00
    deduction_share = 10 / 170 = 0.058824 → 0.0588
    """

    def setup_method(self):
        self.result = compute_trip_summary(
            trips=[
                t(base=80, inc=20, tip=10, deds=[10.0], total=100.0, km=5, mins=25),
                t(base=60, km=3, mins=15),
            ],
            costs=costs(),
            logged_in_hours=1.5,
        )

    def test_gross_pay(self):
        assert self.result.gross_pay == 170.0

    def test_net_payout(self):
        assert self.result.net_payout == 160.0

    def test_worker_costs(self):
        assert self.result.worker_costs == 32.0

    def test_net_earnings(self):
        assert self.result.net_earnings == 128.0

    def test_per_engaged_hour(self):
        assert self.result.net_per_engaged_hour == 192.0

    def test_per_logged_in_hour(self):
        assert self.result.net_per_logged_in_hour == 85.33

    def test_per_km(self):
        assert self.result.net_payout_per_km == 20.0

    def test_deduction_share(self):
        assert self.result.deduction_share == 0.0588


# ---------------------------------------------------------------------------
# Additional trip-mode cases
# ---------------------------------------------------------------------------

def test_trip_empty_list_returns_none_metrics():
    """No trips at all: every metric is None; trip_count is 0."""
    r = compute_trip_summary(trips=[], costs=costs())
    assert r.trip_count == 0
    assert r.gross_pay is None
    assert r.net_earnings is None
    assert r.net_per_engaged_hour is None
    assert "No trips" in r.data_quality[0]


def test_trip_zero_distance_returns_none_per_km():
    """Trip with zero distance recorded.

    Trip: base 100, 0 km, 30 min
    gross = 100, deductions = 0, net_payout = 100
    total_distance = 0  →  per_km = None (zero denominator)
    worker_costs = 0 * 4 = 0
    net_earnings = 100 - 0 = 100
    per_engaged_hour = 100 / (30/60) = 100 / 0.5 = 200.00
    """
    r = compute_trip_summary(
        trips=[t(base=100, km=0, mins=30)],
        costs=costs(),
    )
    assert r.net_payout_per_km is None
    assert r.worker_costs == 0.0
    assert r.net_per_engaged_hour == 200.0
    assert any("zero" in note for note in r.data_quality)


def test_trip_zero_duration_returns_none_per_engaged_hour():
    """Trip with zero duration.

    Trip: base 50, 5 km, 0 min
    engaged_hours = 0  →  per_engaged_hour = None
    net_payout = 50
    worker_costs = 5 * 4 = 20
    net_earnings = 50 - 20 = 30
    per_km = 50 / 5 = 10.00
    """
    r = compute_trip_summary(
        trips=[t(base=50, km=5, mins=0)],
        costs=costs(),
    )
    assert r.net_per_engaged_hour is None
    assert r.net_payout_per_km == 10.0
    assert r.net_earnings == 30.0


def test_trip_reconciliation_gap_flagged():
    """A trip where computed pay ≠ total_payout by > 0.5 gets flagged.

    Trip: base 100, total_payout 50 → gap = 100 - 50 = 50 > 0.5
    gross = 100, net_payout = 100
    (engine uses the component fields, not total_payout, for all calculations)
    """
    r = compute_trip_summary(
        trips=[t(base=100, km=4, mins=20, total=50.0)],
        costs=costs(),
    )
    assert any("add up" in note for note in r.data_quality)
    # gross and net_payout come from components, not total_payout
    assert r.gross_pay == 100.0
    assert r.net_payout == 100.0


def test_trip_several_deductions():
    """Multiple deductions across multiple trips.

    Trip 1: base 200, deds [20, 15], km 10, min 40
    Trip 2: base 150, deds [10], km 8, min 30

    gross = 200 + 150 = 350
    platform_deductions = (20+15) + 10 = 45
    net_payout = 350 - 45 = 305
    total_distance = 18 km
    worker_costs = 18 * 4 = 72
    net_earnings = 305 - 72 = 233
    engaged_hours = 70/60 ≈ 1.1667
    per_engaged_hour = 233 / (70/60) = 233 * 60/70 ≈ 199.71
    per_km = 305 / 18 ≈ 16.94
    deduction_share = 45 / 350 ≈ 0.1286
    """
    r = compute_trip_summary(
        trips=[
            t(base=200, deds=[20.0, 15.0], km=10, mins=40),
            t(base=150, deds=[10.0], km=8, mins=30),
        ],
        costs=costs(),
    )
    assert r.gross_pay == 350.0
    assert r.platform_deductions == 45.0
    assert r.net_payout == 305.0
    assert r.worker_costs == 72.0
    assert r.net_earnings == 233.0
    assert r.net_per_engaged_hour == round(233 / (70 / 60), 2)
    assert r.net_payout_per_km == round(305 / 18, 2)
    assert r.deduction_share == round(45 / 350, 4)


def test_trip_single_trip_no_deductions():
    """Single trip, no extras.

    Trip: base 120, 6 km, 24 min, logged_in_hours=0.5
    gross = 120, deductions = 0, net_payout = 120
    worker_costs = 6 * 4 = 24
    net_earnings = 120 - 24 = 96
    engaged_hours = 24/60 = 0.4
    per_engaged_hour = 96 / 0.4 = 240.00
    per_logged_in_hour = 96 / 0.5 = 192.00
    per_km = 120 / 6 = 20.00
    deduction_share = 0 / 120 = 0.0
    """
    r = compute_trip_summary(
        trips=[t(base=120, km=6, mins=24)],
        costs=costs(),
        logged_in_hours=0.5,
    )
    assert r.gross_pay == 120.0
    assert r.platform_deductions == 0.0
    assert r.net_earnings == 96.0
    assert r.net_per_engaged_hour == 240.0
    assert r.net_per_logged_in_hour == 192.0
    assert r.deduction_share == 0.0


def test_trip_negative_input_rejected():
    """Negative base_pay must raise ValueError."""
    with pytest.raises(ValueError, match="base_pay"):
        compute_trip_summary(trips=[t(base=-10, km=5, mins=20)], costs=costs())


def test_trip_negative_fuel_cost_rejected():
    """Negative fuel cost must raise ValueError."""
    with pytest.raises(ValueError, match="fuel_cost_per_km"):
        compute_trip_summary(trips=[t(base=50, km=5, mins=20)], costs=costs(fuel=-1))


def test_trip_missing_distance_notes_quality():
    """Trips without distance data: per-km and worker costs are None.

    Trip 1: base 100, 5 km, 30 min
    Trip 2: base 80, km=None, 20 min

    total_distance (known trips only) = 5 km
    Missing 1 trip's distance → data_quality note; per-km and costs computed
    from partial data with a quality note.
    """
    r = compute_trip_summary(
        trips=[
            t(base=100, km=5, mins=30),
            t(base=80, km=None, mins=20),
        ],
        costs=costs(),
    )
    assert r.total_distance_km == 5.0
    # There IS distance data (partial), so worker_costs is computed from what we have
    assert r.worker_costs is not None
    assert any("distance" in note for note in r.data_quality)


def test_trip_large_list():
    """50 identical trips to check no overflow or rounding issues.

    Each trip: base 100, km 5, min 30
    gross = 50 * 100 = 5000
    worker_costs = 50*5 * 4 = 1000
    net_earnings = 5000 - 1000 = 4000
    per_engaged_hour = 4000 / (50*30/60) = 4000 / 25 = 160.0
    per_km = 5000 / 250 = 20.0
    """
    many = [t(base=100, km=5, mins=30) for _ in range(50)]
    r = compute_trip_summary(trips=many, costs=costs())
    assert r.gross_pay == 5000.0
    assert r.worker_costs == 1000.0
    assert r.net_earnings == 4000.0
    assert r.net_per_engaged_hour == 160.0
    assert r.net_payout_per_km == 20.0


def test_trip_fixed_cost_per_day():
    """Fixed daily cost included when period_days is given.

    Trip: base 100, km 5, min 30
    Fuel 2.0, maint 1.0, fixed 20.0/day, period_days=3
    worker_costs = 5*3 + 20*3 = 15 + 60 = 75
    net_earnings = 100 - 75 = 25
    """
    r = compute_trip_summary(
        trips=[t(base=100, km=5, mins=30)],
        costs=costs(fuel=2.0, maint=1.0, fixed=20.0),
        period_days=3,
    )
    assert r.worker_costs == 75.0
    assert r.net_earnings == 25.0


# ===========================================================================
# WEEKLY MODE
# ===========================================================================

class TestWeeklyWorkedExample:
    """REQUIREMENTS.md section 5.2 worked example.

    Lines: order earnings 7000, daily incentive 1500
    Deduction: platform charges 300
    Total credited: 8200
    Worker enters: 520 km, 48 hours online; fuel 3.0, maintenance 1.0

    gross = 7000 + 1500 = 8500
    deductions = 300
    net_payout = 8500 - 300 = 8200
    reconciliation_gap = 8200 - 8200 = 0
    worker_costs = 520 * (3+1) = 520 * 4 = 2080
    net_earnings = 8200 - 2080 = 6120
    per_online_hour = 6120 / 48 = 127.50
    per_km = 8200 / 520 = 15.769... → 15.77
    deduction_share = 300 / 8500 = 0.035294 → 0.0353
    """

    def setup_method(self):
        self.result = compute_weekly_summary(
            week=week(
                {"Order earnings": 7000.0, "Daily incentive": 1500.0},
                deds=[300.0], credited=8200.0, km=520.0, hours=48.0,
            ),
            costs=costs(),
        )

    def test_gross_weekly(self):
        assert self.result.gross_weekly == 8500.0

    def test_net_payout_weekly(self):
        assert self.result.net_payout_weekly == 8200.0

    def test_reconciliation_gap_zero(self):
        assert self.result.reconciliation_gap == 0.0

    def test_worker_costs(self):
        assert self.result.worker_costs_weekly == 2080.0

    def test_net_earnings(self):
        assert self.result.net_earnings_weekly == 6120.0

    def test_per_online_hour(self):
        assert self.result.net_per_online_hour == 127.5

    def test_per_km(self):
        assert self.result.net_payout_per_km == 15.77

    def test_deduction_share(self):
        assert self.result.deduction_share == 0.0353

    def test_per_hour_on_trips_unavailable(self):
        assert "not available" in self.result.per_hour_on_trips_unavailable
        assert "weekly" in self.result.per_hour_on_trips_unavailable.lower()


# ---------------------------------------------------------------------------
# Additional weekly-mode cases
# ---------------------------------------------------------------------------

def test_weekly_no_km_returns_none_costs():
    """No km_driven: worker_costs and per-km are None.

    Lines: 5000. Deductions: 200. Hours: 40.
    gross = 5000, net_payout = 4800
    worker_costs = None (no km)  →  net_earnings = None  →  per_online_hour = None
    """
    r = compute_weekly_summary(
        week=week({"Earnings": 5000.0}, deds=[200.0], hours=40.0),
        costs=costs(),
    )
    assert r.worker_costs_weekly is None
    assert r.net_earnings_weekly is None
    assert r.net_per_online_hour is None
    assert r.net_payout_per_km is None
    assert any("Distance driven" in note for note in r.data_quality)


def test_weekly_no_hours_returns_none_per_hour():
    """No hours_online: per_online_hour is None; km-based metrics still computed.

    Lines: 6000. Km: 300.
    gross = 6000, net_payout = 6000
    worker_costs = 300 * 4 = 1200
    net_earnings = 6000 - 1200 = 4800
    per_online_hour = None (no hours)
    per_km = 6000 / 300 = 20.0
    """
    r = compute_weekly_summary(
        week=week({"Base": 6000.0}, km=300.0),
        costs=costs(),
    )
    assert r.net_per_online_hour is None
    assert r.net_payout_per_km == 20.0
    assert r.net_earnings_weekly == 4800.0
    assert any("Hours online" in note for note in r.data_quality)


def test_weekly_zero_km_returns_none_per_km():
    """Zero km_driven: per_km is None; per_online_hour may still be computed.

    Lines: 4000. Km: 0. Hours: 20.
    gross = 4000, net_payout = 4000
    worker_costs = 0 * 4 = 0
    net_earnings = 4000 - 0 = 4000
    per_km = None (zero denominator)
    per_online_hour = 4000 / 20 = 200.0
    """
    r = compute_weekly_summary(
        week=week({"Earnings": 4000.0}, km=0.0, hours=20.0),
        costs=costs(),
    )
    assert r.net_payout_per_km is None
    assert r.worker_costs_weekly == 0.0
    assert r.net_per_online_hour == 200.0
    assert any("zero" in note for note in r.data_quality)


def test_weekly_total_credited_missing_no_recon():
    """When total_credited is None, reconciliation_gap is None (no flag).

    Lines: 3000. Km: 150. Hours: 30.
    """
    r = compute_weekly_summary(
        week=week({"Order": 3000.0}, km=150.0, hours=30.0),
        costs=costs(),
    )
    assert r.reconciliation_gap is None
    # No reconciliation quality note expected
    assert not any("add up" in note for note in r.data_quality)


def test_weekly_reconciliation_gap_flagged():
    """total_credited differs from net_payout by > 0.5 → data_quality note.

    Lines: 5000. Deductions: 0. total_credited: 4000. Gap = 4000-5000 = -1000.
    """
    r = compute_weekly_summary(
        week=week({"Base": 5000.0}, credited=4000.0, km=100.0, hours=10.0),
        costs=costs(),
    )
    assert r.reconciliation_gap == -1000.0
    assert any("add up" in note for note in r.data_quality)


def test_weekly_negative_deduction_rejected():
    """Negative deduction must raise ValueError."""
    with pytest.raises(ValueError, match="deductions"):
        compute_weekly_summary(
            week=week({"Base": 5000.0}, deds=[-10.0], km=100.0, hours=10.0),
            costs=costs(),
        )


def test_weekly_negative_km_rejected():
    """Negative km_driven must raise ValueError."""
    with pytest.raises(ValueError, match="km_driven"):
        compute_weekly_summary(
            week=week({"Base": 5000.0}, km=-50.0, hours=10.0),
            costs=costs(),
        )


def test_weekly_with_fixed_daily_cost():
    """Fixed daily cost included in worker costs.

    Lines: 8000. Km: 400. Hours: 40. Fuel 2.0, maint 1.0, fixed 50/day, 7 days.
    worker_costs = 400*(2+1) + 50*7 = 1200 + 350 = 1550
    net_earnings = 8000 - 1550 = 6450
    per_online_hour = 6450 / 40 = 161.25
    per_km = 8000 / 400 = 20.0
    """
    r = compute_weekly_summary(
        week=week({"Base": 8000.0}, km=400.0, hours=40.0),
        costs=costs(fuel=2.0, maint=1.0, fixed=50.0),
        period_days=7,
    )
    assert r.worker_costs_weekly == 1550.0
    assert r.net_earnings_weekly == 6450.0
    assert r.net_per_online_hour == 161.25
    assert r.net_payout_per_km == 20.0


def test_weekly_several_lines_and_deductions():
    """Multiple payout lines and multiple deductions.

    Lines: base 5000, incentive 1000, bonus 500 = 6500
    Deductions: [200, 100] = 300
    net_payout = 6200
    Km: 310. Hours: 50. Fuel 3.0, maint 1.0.
    worker_costs = 310 * 4 = 1240
    net_earnings = 6200 - 1240 = 4960
    per_online_hour = 4960 / 50 = 99.2
    per_km = 6200 / 310 ≈ 20.0
    deduction_share = 300 / 6500 ≈ 0.0462
    """
    r = compute_weekly_summary(
        week=week(
            {"Base": 5000.0, "Incentive": 1000.0, "Bonus": 500.0},
            deds=[200.0, 100.0], km=310.0, hours=50.0,
        ),
        costs=costs(),
    )
    assert r.gross_weekly == 6500.0
    assert r.deductions_weekly == 300.0
    assert r.net_payout_weekly == 6200.0
    assert r.worker_costs_weekly == 1240.0
    assert r.net_earnings_weekly == 4960.0
    assert r.net_per_online_hour == round(4960 / 50, 2)
    assert r.net_payout_per_km == round(6200 / 310, 2)
    assert r.deduction_share == round(300 / 6500, 4)


# ===========================================================================
# CHANGE DETECTION (engine/changes.py)
# ===========================================================================

def _make_trips(n: int, km: float, pay: float, confirmed: bool = True):
    """Make n identical trips with given pay per km (net, no deductions)."""
    return [
        TripInput(base_pay=pay * km, distance_km=km, duration_min=30,
                  date_confirmed=confirmed)
        for _ in range(n)
    ]


def test_changes_possible_change():
    """A 20% pay cut across 20 baseline + 20 recent trips must be detected.

    Baseline: 20 trips, pay 20.0/km, km 5 → metric 20.0
    Recent:   20 trips, pay 16.0/km, km 5 → metric 16.0
    Relative change = (16-20)/20 = -0.20, which exceeds the 5% threshold.
    Bootstrap CI should exclude 0 for such a clear separation.
    """
    baseline = _make_trips(20, km=5.0, pay=20.0)
    recent = _make_trips(20, km=5.0, pay=16.0)
    r = detect_change(baseline, recent)
    assert r.status == "possible_change"
    assert r.ci_high is not None and r.ci_high < 0  # CI entirely below 0 (cut)
    assert r.relative_change is not None and r.relative_change < -0.05


def test_changes_no_clear_change():
    """Identical pay in both periods: no clear change.

    Baseline: 20 trips, pay 20.0/km, km 5
    Recent:   20 trips, pay 20.0/km, km 5
    Relative change = 0; CI straddles 0.
    """
    baseline = _make_trips(20, km=5.0, pay=20.0)
    recent = _make_trips(20, km=5.0, pay=20.0)
    r = detect_change(baseline, recent)
    assert r.status == "no_clear_change"


def test_changes_insufficient_data_baseline():
    """Fewer than 15 confirmed trips in the baseline → insufficient_data.

    Baseline: 10 trips. Recent: 20 trips. Min is 15.
    """
    baseline = _make_trips(10, km=5.0, pay=20.0)
    recent = _make_trips(20, km=5.0, pay=20.0)
    r = detect_change(baseline, recent)
    assert r.status == "insufficient_data"
    assert r.baseline_count == 10


def test_changes_insufficient_data_recent():
    """Fewer than 15 confirmed trips in the recent period → insufficient_data."""
    baseline = _make_trips(20, km=5.0, pay=20.0)
    recent = _make_trips(5, km=5.0, pay=16.0)
    r = detect_change(baseline, recent)
    assert r.status == "insufficient_data"
    assert r.recent_count == 5


def test_changes_unconfirmed_dates_excluded():
    """Trips with date_confirmed=False must be excluded from analysis.

    Provide 20 confirmed + 10 unconfirmed in each period.
    Only the 20 confirmed trips count. With 20 each, the test can run.
    The unconfirmed count must be reported.
    """
    confirmed_b = _make_trips(20, km=5.0, pay=20.0, confirmed=True)
    unconfirmed_b = _make_trips(10, km=5.0, pay=20.0, confirmed=False)
    confirmed_r = _make_trips(20, km=5.0, pay=16.0, confirmed=True)
    unconfirmed_r = _make_trips(10, km=5.0, pay=16.0, confirmed=False)

    r = detect_change(confirmed_b + unconfirmed_b, confirmed_r + unconfirmed_r)
    assert r.excluded_unconfirmed == 20
    assert r.baseline_count == 20
    assert r.recent_count == 20
    assert r.status == "possible_change"
    assert "date_confirmed" in (r.reason or "")


def test_changes_all_unconfirmed_returns_insufficient():
    """All trips unconfirmed → excluded → insufficient_data reported."""
    baseline = _make_trips(20, km=5.0, pay=20.0, confirmed=False)
    recent = _make_trips(20, km=5.0, pay=16.0, confirmed=False)
    r = detect_change(baseline, recent)
    assert r.status == "insufficient_data"
    assert r.excluded_unconfirmed == 40


def test_changes_small_change_below_threshold():
    """A 3% pay difference: CI may exclude 0 but relative change < 5% → no_clear_change.

    Baseline: 30 trips, metric exactly 20.0
    Recent:   30 trips, metric exactly 20.6  (3%)
    Both periods are identical so CI straddles 0 anyway, confirming no_clear_change.
    """
    baseline = _make_trips(30, km=5.0, pay=20.0)
    recent = _make_trips(30, km=5.0, pay=20.6)
    r = detect_change(baseline, recent)
    # 3% < 5% threshold; even if CI happened to exclude 0, no_clear_change is correct
    # (in practice CI spans 0 for identical-trip populations with 3% difference)
    assert r.status in ("no_clear_change", "possible_change")
    # Specifically: same-distribution bootstrap — CI will include 0
    assert r.status == "no_clear_change"


def test_changes_missing_distance_excluded_from_metric():
    """Trips without distance are excluded from metric but do not crash.

    Provide 20 trips without km and 20 with km in each period.
    Only the 20 with km count for the metric.
    """
    no_km = [TripInput(base_pay=100, distance_km=None, duration_min=30, date_confirmed=True)
             for _ in range(20)]
    with_km_b = _make_trips(20, km=5.0, pay=20.0)
    with_km_r = _make_trips(20, km=5.0, pay=16.0)

    r = detect_change(no_km + with_km_b, no_km + with_km_r)
    assert r.status == "possible_change"
    assert r.baseline_count == 20
    assert r.recent_count == 20
