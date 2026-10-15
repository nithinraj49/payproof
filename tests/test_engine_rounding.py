"""Money rounding is Decimal ROUND_HALF_UP (an exact half rounds up), and the
data-quality notes use plain wording with human numbering and engine amounts."""
from engine.earnings import compute_trip_summary, compute_weekly_summary
from engine.models import CostInputs, PayoutLine, TripInput, WeekInput

COSTS_34 = CostInputs(fuel_cost_per_km=3, maintenance_cost_per_km=1)
NO_COSTS = CostInputs(fuel_cost_per_km=0, maintenance_cost_per_km=0)


def test_weekly_per_hour_exact_half_rounds_up_to_195_58():
    # lines 7345 + 1678 = 9023; costs 300 km * 4 = 1200; net 7823; 7823 / 40 = 195.575 exactly.
    week = WeekInput(
        lines=[PayoutLine(label="Orders", amount=7345), PayoutLine(label="Incentive", amount=1678)],
        deductions=[], total_credited=10120, km_driven=300, hours_online=40,
    )
    s = compute_weekly_summary(week, COSTS_34)
    assert s.net_earnings_weekly == 7823.0
    assert s.net_per_online_hour == 195.58  # float round() would give 195.57
    assert s.net_payout_per_km == 30.08
    assert s.reconciliation_gap == 1097.0


def test_trip_per_km_exact_half_rounds_up():
    # 100.5 / 4 km = 25.125 exactly: half up gives 25.13 (float round() gives 25.12).
    t = TripInput(base_pay=100.5, total_payout=100.5, distance_km=4, duration_min=30)
    s = compute_trip_summary([t], NO_COSTS)
    assert s.net_payout_per_km == 25.13


def test_trip_per_hour_exact_half_rounds_up():
    # net 100.5 over 4 hours (240 min) is 25.125 per hour exactly.
    t = TripInput(base_pay=100.5, total_payout=100.5, distance_km=10, duration_min=240)
    assert compute_trip_summary([t], NO_COSTS).net_per_engaged_hour == 25.13


def test_deduction_share_keeps_four_decimals():
    t = TripInput(base_pay=80, incentive=20, tip=10, deductions=[10], total_payout=100, distance_km=5, duration_min=25)
    t2 = TripInput(base_pay=60, total_payout=60, distance_km=3, duration_min=15)
    s = compute_trip_summary([t, t2], COSTS_34, logged_in_hours=1.5)
    assert s.deduction_share == 0.0588
    assert (s.net_earnings, s.net_per_engaged_hour, s.net_per_logged_in_hour, s.net_payout_per_km) == (128.0, 192.0, 85.33, 20.0)


def test_trip_mismatch_note_has_human_numbering_and_engine_amounts():
    t = TripInput(base_pay=136.65, incentive=0.37, tip=10, total_payout=136.65, distance_km=5, duration_min=25)
    notes = compute_trip_summary([t], COSTS_34).data_quality
    assert "Trip 1: the amounts add up to ₹147.02, but its screenshot says ₹136.65." in notes
    assert not any("[" in n or "gap" in n or "(s)" in n for n in notes)


def test_second_trip_is_numbered_two_and_indian_grouping_used():
    ok = TripInput(base_pay=100, total_payout=100, distance_km=1, duration_min=10)
    bad = TripInput(base_pay=123456.0, total_payout=100000.0, distance_km=1, duration_min=10)
    notes = compute_trip_summary([ok, bad], NO_COSTS).data_quality
    assert "Trip 2: the amounts add up to ₹1,23,456.00, but its screenshot says ₹1,00,000.00." in notes


def test_other_notes_are_plain_words_not_field_names():
    t = TripInput(base_pay=None, total_payout=None, distance_km=None, duration_min=None)
    notes = " ".join(compute_trip_summary([t], COSTS_34).data_quality)
    for raw in ("null", "base_pay", "gross_pay", "_hours", "(s)", "metrics"):
        assert raw not in notes
    assert "1 trip has no base pay" in notes
    week = WeekInput(lines=[PayoutLine(label="x", amount=10)], deductions=[], total_credited=None, km_driven=None, hours_online=None)
    wnotes = " ".join(compute_weekly_summary(week, COSTS_34).data_quality)
    for raw in ("km_driven", "hours_online", "total_credited", "—"):
        assert raw not in wnotes
