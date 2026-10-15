"""Tests for POST /api/trip-reconciliation and engine.reconcile_trips: a
stateless pre-save check so the trip review screen can warn when base pay +
incentive + tip - deductions differs from the screenshot's total payout by
more than 0.5. No Firestore, no Gemini, no network.
"""
import pytest
from fastapi.testclient import TestClient

from backend.auth import require_user_id
from backend.main import app
from backend.report import render_trip_report
from engine.earnings import compute_trip_summary, reconcile_trips
from engine.models import CostInputs, TripInput

client = TestClient(app)


def setup_module(module):
    app.dependency_overrides[require_user_id] = lambda: "test-uid"


def teardown_module(module):
    app.dependency_overrides.pop(require_user_id, None)


def _trip(**kw):
    base = {"base_pay": 80.0, "incentive": 20.0, "tip": 10.0,
            "deductions": [{"label": "Platform fee", "amount": 10.0}], "total_payout": 100.0}
    base.update(kw)
    return base


def _post(trips):
    return client.post("/api/trip-reconciliation", json={"trips": trips})


def test_matching_trip_is_not_flagged():
    body = _post([_trip()]).json()
    assert body["flagged_count"] == 0
    assert body["flagged"] == []


def test_gap_over_tolerance_is_flagged_with_engine_figures():
    # 80 + 20 + 10 - 10 = 100, but the screenshot says 92.
    response = _post([_trip(total_payout=92.0)])
    assert response.status_code == 200
    body = response.json()
    assert body["flagged_count"] == 1
    assert body["flagged"][0] == {"trip_index": 0, "computed_total": 100.0, "total_payout": 92.0, "gap": 8.0}


def test_gap_exactly_at_tolerance_is_not_flagged():
    assert _post([_trip(total_payout=99.5)]).json()["flagged_count"] == 0
    assert _post([_trip(total_payout=100.5)]).json()["flagged_count"] == 0


def test_gap_just_over_tolerance_is_flagged():
    assert _post([_trip(total_payout=99.4)]).json()["flagged_count"] == 1


def test_trip_without_total_payout_cannot_be_checked():
    assert _post([_trip(total_payout=None)]).json()["flagged_count"] == 0


def test_only_the_bad_trip_is_flagged_by_index():
    body = _post([_trip(), _trip(total_payout=50.0), _trip()]).json()
    assert [f["trip_index"] for f in body["flagged"]] == [1]


def test_missing_parts_count_as_zero():
    # base 60 only, total 60: fine. Same trip with total 80: flagged.
    ok = _trip(base_pay=60.0, incentive=None, tip=None, deductions=[], total_payout=60.0)
    bad = dict(ok, total_payout=80.0)
    assert _post([ok]).json()["flagged_count"] == 0
    assert _post([bad]).json()["flagged"][0]["computed_total"] == 60.0


def test_negative_amount_is_rejected_not_500():
    assert _post([_trip(base_pay=-1.0)]).status_code == 422


def test_requires_auth():
    app.dependency_overrides.pop(require_user_id, None)
    try:
        assert _post([_trip()]).status_code == 401
    finally:
        app.dependency_overrides[require_user_id] = lambda: "test-uid"


def test_does_not_touch_firestore(monkeypatch):
    import backend.main as main_module
    calls = []
    monkeypatch.setattr(main_module, "save_trips", lambda *a, **k: calls.append(a))
    _post([_trip(total_payout=1.0)])
    assert calls == []


def test_engine_reconcile_trips_directly():
    trips = [TripInput(base_pay=80, incentive=20, tip=10, deductions=[10], total_payout=100),
             TripInput(base_pay=60, total_payout=70)]
    flagged = reconcile_trips(trips)
    assert len(flagged) == 1
    assert (flagged[0].trip_index, flagged[0].computed_total, flagged[0].gap) == (1, 60.0, -10.0)


def test_engine_reconcile_trips_rejects_negative():
    with pytest.raises(ValueError):
        reconcile_trips([TripInput(base_pay=-5, total_payout=10)])


def test_evidence_pack_shows_amber_note_only_when_flagged():
    trips = [TripInput(base_pay=80, incentive=20, tip=10, deductions=[10], total_payout=92,
                       distance_km=5, duration_min=25)]
    summary = compute_trip_summary(trips, CostInputs(fuel_cost_per_km=3, maintenance_cost_per_km=1))
    flagged = reconcile_trips(trips)
    html_flagged = render_trip_report(summary, [], flagged)
    assert "recon-warning" in html_flagged
    assert "add up to ₹100.00" in html_flagged and "₹92.00 was paid" in html_flagged
    assert 'class="recon-warning"' not in render_trip_report(summary, [], [])
    assert 'class="recon-warning"' not in render_trip_report(summary, [])


def test_summary_endpoint_reports_flagged_trip_count(monkeypatch):
    import backend.main as main_module
    rows = [
        {"base_pay": 80, "incentive": 20, "tip": 10, "deductions": [{"label": "fee", "amount": 10}],
         "total_payout": 92, "distance_km": 5, "duration_min": 25},
        {"base_pay": 60, "total_payout": 60, "distance_km": 3, "duration_min": 15, "deductions": []},
    ]
    monkeypatch.setattr(main_module, "get_trips", lambda uid: rows)
    monkeypatch.setattr(main_module, "get_costs", lambda uid: {"fuel_cost_per_km": 3, "maintenance_cost_per_km": 1})
    body = client.get("/api/summary?mode=trip").json()
    assert body["reconciliation_flagged_trips"] == 1
