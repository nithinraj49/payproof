"""Tests for GET /api/report. Firestore and auth are mocked/overridden;
no network calls."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.auth import require_user_id
from backend.main import app

client = TestClient(app)


def setup_module(module):
    app.dependency_overrides[require_user_id] = lambda: "test-uid"


def teardown_module(module):
    app.dependency_overrides.pop(require_user_id, None)


def test_report_requires_auth():
    app.dependency_overrides.pop(require_user_id, None)
    try:
        response = client.get("/api/report")
        assert response.status_code == 401
    finally:
        app.dependency_overrides[require_user_id] = lambda: "test-uid"


def test_report_trip_mode_without_costs_returns_400():
    with patch("backend.main.get_costs", return_value=None):
        response = client.get("/api/report")
    assert response.status_code == 400
    assert response.json()["error_code"] == "costs_not_set"


def test_report_trip_mode_without_trips_returns_400():
    with patch("backend.main.get_costs", return_value={"fuel_cost_per_km": 0.0, "maintenance_cost_per_km": 0.0}), \
         patch("backend.main.get_trips", return_value=[]):
        response = client.get("/api/report")
    assert response.status_code == 400
    assert response.json()["error_code"] == "no_trips"


def test_report_trip_mode_returns_self_contained_html():
    trip_rows = [{
        "base_pay": 100.0, "incentive": 0.0, "tip": 0.0, "total_payout": 90.0,
        "distance_km": 6.4, "duration_min": 40.0, "deductions": [{"label": "Platform fee", "amount": 10.0}],
    }]
    with patch("backend.main.get_costs", return_value={"fuel_cost_per_km": 0.0, "maintenance_cost_per_km": 0.0}), \
         patch("backend.main.get_trips", return_value=trip_rows):
        response = client.get("/api/report")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "<html" in body.lower()
    assert "Platform fee" in body
    assert "Built only from the screenshots you provided" in body
    assert "₹90.00" in body  # net payout, with currency


def test_report_weekly_mode_uses_the_most_recently_saved_week():
    week_rows = [
        {"lines": [{"label": "Old", "amount": 1.0}], "deductions": [], "total_credited": 1.0, "km_driven": 1.0, "hours_online": 1.0, "saved_at": "2026-01-01T00:00:00"},
        {"lines": [{"label": "Newest", "amount": 100.0}], "deductions": [], "total_credited": 100.0, "km_driven": 10.0, "hours_online": 5.0, "saved_at": "2026-02-01T00:00:00"},
    ]
    with patch("backend.main.get_costs", return_value={"fuel_cost_per_km": 0.0, "maintenance_cost_per_km": 0.0}), \
         patch("backend.main.get_weeks", return_value=week_rows):
        response = client.get("/api/report", params={"mode": "weekly"})

    assert response.status_code == 200
    assert "Newest" in response.text
    assert "Old" not in response.text


def test_report_weekly_mode_without_weeks_returns_400():
    with patch("backend.main.get_costs", return_value={"fuel_cost_per_km": 0.0, "maintenance_cost_per_km": 0.0}), \
         patch("backend.main.get_weeks", return_value=[]):
        response = client.get("/api/report", params={"mode": "weekly"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "no_weeks"
