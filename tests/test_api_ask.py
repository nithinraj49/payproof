"""Tests for POST /api/ask. Gemini, Firestore and auth are all mocked or
overridden; no network calls."""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import backend.main as main_module
from backend.auth import require_user_id
from backend.main import app
from backend.qa import AnswerResult
from extraction.extract import RateLimitError

client = TestClient(app)


def setup_module(module):
    app.dependency_overrides[require_user_id] = lambda: "test-uid"


def teardown_module(module):
    app.dependency_overrides.pop(require_user_id, None)


def _settings(**overrides):
    from backend.config import get_settings
    base = get_settings()
    return base.__class__(**{**base.__dict__, **overrides})


def test_ask_rejects_a_non_english_language():
    response = client.post("/api/ask", json={"question": "What was my net pay?", "language": "hi"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "unsupported_language"


def test_ask_rejects_an_empty_question():
    response = client.post("/api/ask", json={"question": ""})
    assert response.status_code == 422


def test_ask_returns_a_verified_answer_and_stores_it(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())
    monkeypatch.setattr(main_module, "check_and_increment", lambda *a, **k: None)

    answer = AnswerResult(
        text="Your net pay was 192.0 per engaged hour.", verified=True,
        numbers_used={"get_summary": {"net_per_engaged_hour": 192.0}},
        raw_calls=2, prompt_tokens=100, output_tokens=20, thinking_tokens=0,
    )
    ask_mock = MagicMock(return_value=answer)
    monkeypatch.setattr(main_module, "ask_question", ask_mock)

    saved = {}
    def fake_save_answer(uid, row):
        saved["uid"] = uid
        saved["row"] = row
        return "answer-123"
    monkeypatch.setattr(main_module, "save_answer", fake_save_answer)

    response = client.post("/api/ask", json={"question": "What was my net pay per hour?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer_id"] == "answer-123"
    assert body["verified"] is True
    assert body["numbers_used"] == {"get_summary": {"net_per_engaged_hour": 192.0}}
    assert "192" in body["text"]

    # Stored under the authenticated user's own id, never a path/body value.
    assert saved["uid"] == "test-uid"
    assert saved["row"]["verified"] is True
    assert saved["row"]["text"] == answer.text
    ask_mock.assert_called_once()


def test_ask_returns_a_refusal_without_erroring(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())
    monkeypatch.setattr(main_module, "check_and_increment", lambda *a, **k: None)
    monkeypatch.setattr(main_module, "save_answer", lambda uid, row: "answer-456")

    refusal = AnswerResult(
        text="I can't give a verified answer to this: ...", verified=False,
        numbers_used={}, raw_calls=4, prompt_tokens=200, output_tokens=40, thinking_tokens=0,
    )
    monkeypatch.setattr(main_module, "ask_question", lambda *a, **k: refusal)

    response = client.post("/api/ask", json={"question": "What will I earn next month?"})
    assert response.status_code == 200  # a refusal is a normal, successful response
    assert response.json()["verified"] is False


def test_ask_enforces_the_daily_question_limit(monkeypatch):
    from backend.errors import ApiError

    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())

    def raise_limit(*a, **k):
        raise ApiError(429, "daily_limit_reached", "You've reached today's limit for this. Please try again tomorrow.")
    monkeypatch.setattr(main_module, "check_and_increment", raise_limit)

    ask_mock = MagicMock()
    monkeypatch.setattr(main_module, "ask_question", ask_mock)

    response = client.post("/api/ask", json={"question": "What was my net pay?"})
    assert response.status_code == 429
    assert response.json()["error_code"] == "daily_limit_reached"
    ask_mock.assert_not_called()  # the limit is checked before any Gemini call


def test_ask_rate_limit_from_gemini_returns_503(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())
    monkeypatch.setattr(main_module, "check_and_increment", lambda *a, **k: None)

    def raise_rate_limit(*a, **k):
        raise RateLimitError("429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(main_module, "ask_question", raise_rate_limit)

    response = client.post("/api/ask", json={"question": "What was my net pay?"})
    assert response.status_code == 503
    assert response.json()["error_code"] == "service_busy"


def test_ask_requires_auth():
    app.dependency_overrides.pop(require_user_id, None)
    try:
        response = client.post("/api/ask", json={"question": "What was my net pay?"})
        assert response.status_code == 401
    finally:
        app.dependency_overrides[require_user_id] = lambda: "test-uid"
