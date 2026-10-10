"""Unit tests for backend/report.py (REQUIREMENTS.md section 8): pure HTML
rendering from an engine summary + raw rows, no network, no Firestore."""
from engine.earnings import compute_trip_summary, compute_weekly_summary
from engine.models import CostInputs, PayoutLine, TripInput, WeekInput

from backend.report import render_trip_report, render_weekly_report


def test_trip_report_escapes_a_malicious_deduction_label():
    trip_rows = [
        {"base_pay": 100.0, "incentive": 0.0, "tip": 0.0, "distance_km": 5.0, "duration_min": 20.0,
         "total_payout": 90.0, "deductions": [{"label": "<script>alert(1)</script>", "amount": 10.0}]},
    ]
    trips = [TripInput(base_pay=100.0, incentive=0.0, tip=0.0, total_payout=90.0, distance_km=5.0, duration_min=20.0, deductions=[10.0])]
    summary = compute_trip_summary(trips, CostInputs(fuel_cost_per_km=0.0, maintenance_cost_per_km=0.0))

    html = render_trip_report(summary, trip_rows)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_trip_report_contains_summary_numbers_and_method_and_limits():
    trips = [TripInput(base_pay=100.0, incentive=20.0, tip=0.0, total_payout=110.0, distance_km=6.4, duration_min=40.0, deductions=[10.0])]
    summary = compute_trip_summary(trips, CostInputs(fuel_cost_per_km=0.0, maintenance_cost_per_km=0.0))

    html = render_trip_report(summary, [{"deductions": []}])

    assert "<html" in html.lower()
    assert str(summary.trip_count) in html
    assert "Method" in html
    assert "built only from the screenshots you provided" in html
    assert "<script" not in html.lower() or "alert" not in html.lower()  # sanity: no stray injected script


def test_trip_report_shows_data_quality_notes_when_present():
    # No distance on the only trip -> engine adds a data_quality note.
    trips = [TripInput(base_pay=50.0, total_payout=50.0, duration_min=10.0)]
    summary = compute_trip_summary(trips, CostInputs(fuel_cost_per_km=0.0, maintenance_cost_per_km=0.0))
    assert summary.data_quality  # sanity: the engine actually produced a note

    html = render_trip_report(summary, [{"deductions": []}])
    assert "Data-quality notes" in html
    for note in summary.data_quality:
        assert note in html


def test_trip_report_aggregates_deduction_labels_across_trips():
    trip_rows = [
        {"deductions": [{"label": "Platform fee", "amount": 5.0}]},
        {"deductions": [{"label": "Platform fee", "amount": 3.0}]},
    ]
    trips = [
        TripInput(base_pay=50.0, total_payout=45.0, distance_km=2.0, duration_min=10.0, deductions=[5.0]),
        TripInput(base_pay=40.0, total_payout=37.0, distance_km=2.0, duration_min=10.0, deductions=[3.0]),
    ]
    summary = compute_trip_summary(trips, CostInputs(fuel_cost_per_km=0.0, maintenance_cost_per_km=0.0))
    html = render_trip_report(summary, trip_rows)
    assert "Platform fee" in html
    assert "8" in html  # 5.0 + 3.0 aggregated


def test_weekly_report_escapes_a_malicious_period_label_and_line_label():
    week_row = {
        "period_label": "<img src=x onerror=alert(1)>",
        "lines": [{"label": "<b>Base</b>", "amount": 100.0}],
        "deductions": [{"label": "Fee & Co", "amount": 10.0}],
        "total_credited": 90.0, "km_driven": 10.0, "hours_online": 5.0,
    }
    week_input = WeekInput(
        lines=[PayoutLine(label="<b>Base</b>", amount=100.0)],
        deductions=[10.0], total_credited=90.0, km_driven=10.0, hours_online=5.0,
    )
    summary = compute_weekly_summary(week_input, CostInputs(fuel_cost_per_km=0.0, maintenance_cost_per_km=0.0))

    html = render_weekly_report(summary, week_row)

    assert "<img src=x onerror=alert(1)>" not in html
    assert "<b>Base</b>" not in html
    assert "Fee &amp; Co" in html
    assert "&lt;b&gt;Base&lt;/b&gt;" in html


def test_weekly_report_shows_per_hour_on_trips_unavailable_reason():
    week_input = WeekInput(lines=[PayoutLine(label="Base", amount=100.0)], total_credited=100.0, km_driven=10.0, hours_online=5.0)
    summary = compute_weekly_summary(week_input, CostInputs(fuel_cost_per_km=0.0, maintenance_cost_per_km=0.0))
    html = render_weekly_report(summary, {"lines": [{"label": "Base", "amount": 100.0}], "deductions": []})
    assert summary.per_hour_on_trips_unavailable in html
