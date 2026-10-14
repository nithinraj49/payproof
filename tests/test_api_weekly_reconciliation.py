"""Tests for POST /api/weekly-reconciliation (step 2, 14 Oct 2026): a
stateless pre-save check so the review screen can warn about a missing
earning line before PUT /api/weeks saves anything. No Firestore, no Gemini,
no network -- the endpoint itself never touches either.
"""
from fastapi.testclient import TestClient

from backend.auth import require_user_id
from backend.main import app

client = TestClient(app)


def setup_module(module):
    app.dependency_overrides[require_user_id] = lambda: "test-uid"


def teardown_module(module):
    app.dependency_overrides.pop(require_user_id, None)


def _post(lines, deductions, total_credited):
    return client.post(
        "/api/weekly-reconciliation",
        json={"lines": lines, "deductions": deductions, "total_credited": total_credited},
    )


def test_reconciliation_gap_zero_when_lines_match_total_credited():
    response = _post(
        lines=[{"label": "Order earnings", "amount": 7345.0}, {"label": "Incentive", "amount": 1678.0}],
        deductions=[],
        total_credited=9023.0,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["gross_weekly"] == 9023.0
    assert body["net_payout_weekly"] == 9023.0
    assert body["reconciliation_gap"] == 0.0


def test_reconciliation_gap_positive_when_total_credited_exceeds_lines():
    # The exact owner-provided case: lines 7345 + 1678 = 9023, but the
    # screenshot's total_credited is 10120 -- a line is likely missing.
    response = _post(
        lines=[{"label": "Order earnings", "amount": 7345.0}, {"label": "Incentive", "amount": 1678.0}],
        deductions=[],
        total_credited=10120.0,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["net_payout_weekly"] == 9023.0
    assert body["total_credited"] == 10120.0
    assert body["reconciliation_gap"] == 1097.0


def test_reconciliation_gap_negative_when_lines_exceed_total_credited():
    response = _post(
        lines=[{"label": "Order earnings", "amount": 5000.0}],
        deductions=[{"label": "Platform fee", "amount": 100.0}],
        total_credited=4000.0,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["net_payout_weekly"] == 4900.0
    assert body["reconciliation_gap"] == -900.0


def test_reconciliation_requires_auth():
    app.dependency_overrides.pop(require_user_id, None)
    try:
        response = client.post(
            "/api/weekly-reconciliation",
            json={"lines": [{"label": "Order earnings", "amount": 100.0}], "deductions": [], "total_credited": 100.0},
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides[require_user_id] = lambda: "test-uid"


def test_reconciliation_does_not_touch_firestore(monkeypatch):
    # No store.save_week (or any store function) is imported into this
    # endpoint's code path at all; this test guards against that changing
    # silently by asserting the module-level name is never called.
    import backend.main as main_module
    calls = []
    monkeypatch.setattr(main_module, "save_week", lambda *a, **k: calls.append(a))
    _post(lines=[{"label": "Order earnings", "amount": 100.0}], deductions=[], total_credited=100.0)
    assert calls == []
