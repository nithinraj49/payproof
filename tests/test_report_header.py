"""The evidence-pack header says "1 confirmed trip" or "N confirmed trips",
never the raw "trip(s)"."""
from backend.report import render_trip_report
from engine.earnings import compute_trip_summary
from engine.models import CostInputs, TripInput

COSTS = CostInputs(fuel_cost_per_km=3, maintenance_cost_per_km=1)


def _header(n):
    trips = [TripInput(base_pay=100, total_payout=100, distance_km=2, duration_min=10) for _ in range(n)]
    return render_trip_report(compute_trip_summary(trips, COSTS), [])


def test_singular_for_one_trip():
    html = _header(1)
    assert "trip mode, 1 confirmed trip you uploaded or entered" in html
    assert "trip(s)" not in html


def test_plural_for_several_trips():
    html = _header(3)
    assert "trip mode, 3 confirmed trips you uploaded or entered" in html
    assert "trip(s)" not in html
