"""Unit tests for backend/qa.py's three read-only tools (REQUIREMENTS.md
section 7.1). All Firestore access (backend.store) is mocked -- no network,
no real Firestore.
"""
from unittest.mock import patch

from backend import qa
from engine.earnings import compute_trip_summary
from engine.models import CostInputs, TripInput


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------

def test_get_summary_unavailable_without_costs():
    with patch("backend.qa.get_costs", return_value=None):
        result = qa._tool_get_summary("uid1")
    assert result == {"available": False, "reason": "costs not set"}


def test_get_summary_unavailable_without_trips():
    with patch("backend.qa.get_costs", return_value={"fuel_cost_per_km": 1.0, "maintenance_cost_per_km": 0.5}), \
         patch("backend.qa.get_trips", return_value=[]):
        result = qa._tool_get_summary("uid1")
    assert result == {"available": False, "reason": "no confirmed trips"}


def test_get_summary_matches_the_engine_directly():
    trips_raw = [
        {"base_pay": 60.0, "incentive": 0.0, "tip": 0.0, "deductions": [], "total_payout": 60.0, "distance_km": 3.0, "duration_min": 15.0, "trip_date": None, "date_confirmed": False},
        {"base_pay": 40.0, "incentive": 0.0, "tip": 0.0, "deductions": [], "total_payout": 40.0, "distance_km": 2.0, "duration_min": 10.0, "trip_date": None, "date_confirmed": False},
    ]
    costs_raw = {"fuel_cost_per_km": 0.0, "maintenance_cost_per_km": 0.0}
    expected = compute_trip_summary(
        [
            TripInput(base_pay=60.0, incentive=0.0, tip=0.0, deductions=[], total_payout=60.0, distance_km=3.0, duration_min=15.0),
            TripInput(base_pay=40.0, incentive=0.0, tip=0.0, deductions=[], total_payout=40.0, distance_km=2.0, duration_min=10.0),
        ],
        CostInputs(fuel_cost_per_km=0.0, maintenance_cost_per_km=0.0),
    )
    with patch("backend.qa.get_costs", return_value=costs_raw), patch("backend.qa.get_trips", return_value=trips_raw):
        result = qa._tool_get_summary("uid1")
    assert result["available"] is True
    assert result["net_per_engaged_hour"] == expected.net_per_engaged_hour
    assert result["net_payout_per_km"] == expected.net_payout_per_km
    assert result["deduction_share"] == expected.deduction_share
    # logged_in_hours is never stored -- structurally always unavailable through Q&A.
    assert result["net_per_logged_in_hour"] is None


# ---------------------------------------------------------------------------
# get_trip_stats
# ---------------------------------------------------------------------------

def test_get_trip_stats_zero_trips():
    with patch("backend.qa.get_trips", return_value=[]):
        result = qa._tool_get_trip_stats("uid1")
    assert result == {"available": True, "trip_count": 0}


def test_get_trip_stats_only_counts_confirmed_dates():
    trips = [
        {"trip_date": "2026-01-01", "date_confirmed": True, "distance_km": 3.0, "duration_min": 10.0},
        {"trip_date": "2026-03-01", "date_confirmed": True, "distance_km": None, "duration_min": None},
        {"trip_date": "2026-01-05", "date_confirmed": False, "distance_km": 1.0, "duration_min": 5.0},
    ]
    with patch("backend.qa.get_trips", return_value=trips):
        result = qa._tool_get_trip_stats("uid1")
    assert result["trip_count"] == 3
    assert result["trips_with_confirmed_date"] == 2
    assert result["oldest_confirmed_date"] == "2026-01-01"
    assert result["newest_confirmed_date"] == "2026-03-01"
    assert result["trips_with_distance"] == 2
    assert result["trips_with_duration"] == 2


# ---------------------------------------------------------------------------
# get_weekly
# ---------------------------------------------------------------------------

def test_get_weekly_unavailable_without_costs():
    with patch("backend.qa.get_costs", return_value=None):
        result = qa._tool_get_weekly("uid1")
    assert result == {"available": False, "reason": "costs not set"}


def test_get_weekly_unavailable_without_weeks():
    with patch("backend.qa.get_costs", return_value={"fuel_cost_per_km": 0.0, "maintenance_cost_per_km": 0.0}), \
         patch("backend.qa.get_weeks", return_value=[]):
        result = qa._tool_get_weekly("uid1")
    assert result == {"available": False, "reason": "no confirmed weekly summary"}


def test_get_weekly_reports_per_hour_on_trips_unavailable():
    # FE-7 / REQUIREMENTS.md 5.2: per-trip-hour is structurally unavailable in
    # weekly mode -- the tool must surface this exact reason, not a null.
    week_row = {
        "lines": [{"label": "Base", "amount": 100.0}], "deductions": [],
        "total_credited": 100.0, "km_driven": 10.0, "hours_online": 5.0,
        "saved_at": "2026-01-01T00:00:00",
    }
    costs = {"fuel_cost_per_km": 0.0, "maintenance_cost_per_km": 0.0}
    with patch("backend.qa.get_costs", return_value=costs), patch("backend.qa.get_weeks", return_value=[week_row]):
        result = qa._tool_get_weekly("uid1")
    assert result["available"] is True
    assert result["per_hour_on_trips_unavailable"] == "not available in weekly mode — no per-trip minutes"
