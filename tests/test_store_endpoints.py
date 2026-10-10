"""Tests for backend/store.py and the storage endpoints (PUT trips/weeks/costs,
GET summary/changes, DELETE data). Firestore and auth are mocked; no network.
"""
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.auth import require_user_id
from backend.config import get_settings
from backend.main import app

client = TestClient(app)


def setup_module(module):
    app.dependency_overrides[require_user_id] = lambda: "test-uid"


def teardown_module(module):
    app.dependency_overrides.pop(require_user_id, None)


# ---------------------------------------------------------------------------
# PUT /api/trips
# ---------------------------------------------------------------------------

def test_put_trips_saves_and_returns_ids():
    with patch("backend.main.save_trips", return_value=["id-1", "id-2"]) as mock_save:
        resp = client.put("/api/trips", json={"trips": [
            {"base_pay": 100.0, "distance_km": 5.0, "duration_min": 30.0, "date_confirmed": True},
            {"base_pay": 80.0, "distance_km": 4.0, "duration_min": 20.0, "date_confirmed": False},
        ]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["saved"] == 2
    assert data["trip_ids"] == ["id-1", "id-2"]
    mock_save.assert_called_once()


def test_put_trips_requires_auth():
    app.dependency_overrides.pop(require_user_id, None)
    resp = client.put("/api/trips", json={"trips": []})
    assert resp.status_code == 401
    app.dependency_overrides[require_user_id] = lambda: "test-uid"


def test_put_trips_rejects_negative_base_pay():
    resp = client.put("/api/trips", json={"trips": [{"base_pay": -10.0}]})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/weeks
# ---------------------------------------------------------------------------

def test_put_weeks_saves_week():
    with patch("backend.main.save_week", return_value="week-abc") as mock_save:
        resp = client.put("/api/weeks", json={
            "lines": [{"label": "Order earnings", "amount": 7000.0}],
            "deductions": [{"label": "Fee", "amount": 300.0}],
            "total_credited": 6700.0,
            "km_driven": 400.0,
            "hours_online": 40.0,
        })
    assert resp.status_code == 200
    assert resp.json()["week_id"] == "week-abc"


def test_put_weeks_rejects_negative_km():
    resp = client.put("/api/weeks", json={"km_driven": -10.0, "lines": []})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/costs
# ---------------------------------------------------------------------------

def test_put_costs_saves():
    with patch("backend.main.save_costs") as mock_save:
        resp = client.put("/api/costs", json={"fuel_cost_per_km": 3.0, "maintenance_cost_per_km": 1.0})
    assert resp.status_code == 200
    assert resp.json()["saved"] is True
    mock_save.assert_called_once_with("test-uid", {"fuel_cost_per_km": 3.0, "maintenance_cost_per_km": 1.0, "fixed_cost_per_day": None})


def test_put_costs_rejects_negative_fuel():
    resp = client.put("/api/costs", json={"fuel_cost_per_km": -1.0, "maintenance_cost_per_km": 1.0})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/summary (trip mode)
# ---------------------------------------------------------------------------

STORED_TRIPS = [
    {"base_pay": 80.0, "incentive": 20.0, "tip": 10.0, "deductions": [{"label": "Fee", "amount": 10.0}],
     "total_payout": 100.0, "distance_km": 5.0, "duration_min": 25.0, "date_confirmed": True},
    {"base_pay": 60.0, "deductions": [], "distance_km": 3.0, "duration_min": 15.0, "date_confirmed": True},
]
STORED_COSTS = {"fuel_cost_per_km": 3.0, "maintenance_cost_per_km": 1.0}


def test_get_summary_trip_mode():
    with patch("backend.main.get_trips", return_value=STORED_TRIPS), \
         patch("backend.main.get_costs", return_value=STORED_COSTS):
        resp = client.get("/api/summary?mode=trip&logged_in_hours=1.5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "trip"
    # Worked example values from REQUIREMENTS.md section 5.1
    assert data["gross_pay"] == 170.0
    assert data["net_payout"] == 160.0
    assert data["net_earnings"] == 128.0
    assert data["net_per_engaged_hour"] == 192.0
    assert data["net_per_logged_in_hour"] == 85.33
    assert data["net_payout_per_km"] == 20.0
    assert data["deduction_share"] == 0.0588


def test_get_summary_no_trips_returns_400():
    with patch("backend.main.get_trips", return_value=[]), \
         patch("backend.main.get_costs", return_value=STORED_COSTS):
        resp = client.get("/api/summary?mode=trip")
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "no_trips"


def test_get_summary_no_costs_returns_400():
    with patch("backend.main.get_trips", return_value=STORED_TRIPS), \
         patch("backend.main.get_costs", return_value=None):
        resp = client.get("/api/summary?mode=trip")
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "costs_not_set"


# ---------------------------------------------------------------------------
# GET /api/summary (weekly mode)
# ---------------------------------------------------------------------------

STORED_WEEKS = [{
    "lines": [{"label": "Order earnings", "amount": 7000.0}, {"label": "Daily incentive", "amount": 1500.0}],
    "deductions": [{"label": "Platform charges", "amount": 300.0}],
    "total_credited": 8200.0,
    "km_driven": 520.0,
    "hours_online": 48.0,
    "saved_at": "2026-10-07T10:00:00",
}]


def test_get_summary_weekly_mode():
    with patch("backend.main.get_weeks", return_value=STORED_WEEKS), \
         patch("backend.main.get_costs", return_value=STORED_COSTS):
        resp = client.get("/api/summary?mode=weekly")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "weekly"
    assert data["net_payout_weekly"] == 8200.0
    assert data["net_per_online_hour"] == 127.5
    assert data["net_payout_per_km"] == 15.77
    assert "not available" in data["per_hour_on_trips_unavailable"]


def test_get_summary_no_weeks_returns_400():
    with patch("backend.main.get_weeks", return_value=[]), \
         patch("backend.main.get_costs", return_value=STORED_COSTS):
        resp = client.get("/api/summary?mode=weekly")
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "no_weeks"


# ---------------------------------------------------------------------------
# GET /api/changes
# ---------------------------------------------------------------------------

def _trip_row(base, km, confirmed=True, date="2026-10-01"):
    return {"base_pay": base, "distance_km": km, "duration_min": 30,
            "deductions": [], "date_confirmed": confirmed, "trip_date": date}


TRIPS_WITH_CHANGE = (
    [_trip_row(100, 5, date=f"2026-09-{i:02d}") for i in range(1, 21)] +   # baseline 20
    [_trip_row(80, 5, date=f"2026-10-{i:02d}") for i in range(1, 21)]       # recent 20, -20%
)


def _enabled_settings():
    settings = get_settings()
    return replace(settings, enable_change_signal=True)


def test_get_changes_disabled_by_default():
    """ENABLE_CHANGE_SIGNAL defaults to false: no computation, no trip lookup."""
    with patch("backend.main.get_trips") as mock_get_trips:
        resp = client.get("/api/changes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert "reason" in data
    mock_get_trips.assert_not_called()


def test_get_changes_detects_change():
    with patch("backend.main.get_settings", side_effect=_enabled_settings), \
         patch("backend.main.get_trips", return_value=TRIPS_WITH_CHANGE):
        resp = client.get("/api/changes?split_date=2026-10-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "possible_change"


def test_get_changes_no_trips_returns_400():
    with patch("backend.main.get_settings", side_effect=_enabled_settings), \
         patch("backend.main.get_trips", return_value=[]):
        resp = client.get("/api/changes")
    assert resp.status_code == 400


def test_get_changes_user_id_from_token_not_body(monkeypatch):
    """Another user cannot read this user's changes — the uid comes only from the token."""
    calls = []
    with patch("backend.main.get_settings", side_effect=_enabled_settings), \
         patch("backend.main.get_trips", side_effect=lambda uid: calls.append(uid) or []) as mock:
        client.get("/api/changes")
    assert calls == ["test-uid"]


# ---------------------------------------------------------------------------
# DELETE /api/data
# ---------------------------------------------------------------------------

def test_delete_data_calls_delete_all():
    with patch("backend.main.delete_all", return_value=7) as mock_del:
        resp = client.delete("/api/data")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    assert data["documents_removed"] == 7
    mock_del.assert_called_once_with("test-uid")


def test_delete_data_requires_auth():
    app.dependency_overrides.pop(require_user_id, None)
    resp = client.delete("/api/data")
    assert resp.status_code == 401
    app.dependency_overrides[require_user_id] = lambda: "test-uid"
