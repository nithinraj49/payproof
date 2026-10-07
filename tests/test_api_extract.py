"""Tests for POST /api/extract. Gemini, Firestore and auth are all mocked or
overridden; no network calls."""
import io
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from PIL import Image

import backend.main as main_module
from backend.auth import require_user_id
from backend.main import app
from extraction.extract import ExtractionCallResult, RateLimitError
from extraction.schema import ExtractionResult

client = TestClient(app)


def setup_module(module):
    app.dependency_overrides[require_user_id] = lambda: "test-uid"


def teardown_module(module):
    app.dependency_overrides.pop(require_user_id, None)


def make_png_bytes(size=(300, 200)) -> bytes:
    image = Image.new("RGB", size, (10, 20, 30))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_extract_rejects_unsupported_content_type():
    response = client.post(
        "/api/extract",
        files={"file": ("note.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["error_code"] == "unsupported_file_type"


def test_extract_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(max_upload_mb=0))
    response = client.post(
        "/api/extract",
        files={"file": ("trip.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 413
    assert response.json()["error_code"] == "file_too_large"


def test_extract_rejects_unreadable_image(monkeypatch):
    monkeypatch.setattr(main_module, "get_settings", lambda: _settings())
    response = client.post(
        "/api/extract",
        files={"file": ("trip.png", b"this is not a real image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "unreadable_image"


def test_extract_success_calls_model_once_and_enforces_limits(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())

    check_calls = []
    monkeypatch.setattr(main_module, "check_and_increment", lambda *a, **k: check_calls.append(a))

    result = ExtractionResult(screen_type="trip_detail", needs_review=False)
    outcome = ExtractionCallResult(result=result, calls_made=1, prompt_tokens=100, output_tokens=50, thinking_tokens=0)
    extract_mock = MagicMock(return_value=outcome)
    monkeypatch.setattr(main_module, "extract_screenshot", extract_mock)

    response = client.post(
        "/api/extract",
        files={"file": ("trip.png", make_png_bytes(size=(111, 222)), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["screen_type"] == "trip_detail"
    extract_mock.assert_called_once()
    assert len(check_calls) == 1


def test_extract_second_call_with_same_image_is_served_from_cache(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())
    monkeypatch.setattr(main_module, "check_and_increment", lambda *a, **k: None)

    result = ExtractionResult(screen_type="payout_summary", needs_review=False)
    outcome = ExtractionCallResult(result=result, calls_made=1, prompt_tokens=100, output_tokens=50, thinking_tokens=0)
    extract_mock = MagicMock(return_value=outcome)
    monkeypatch.setattr(main_module, "extract_screenshot", extract_mock)

    image_bytes = make_png_bytes(size=(333, 444))
    r1 = client.post("/api/extract", files={"file": ("w.png", image_bytes, "image/png")})
    r2 = client.post("/api/extract", files={"file": ("w.png", image_bytes, "image/png")})

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    extract_mock.assert_called_once()  # second call served from cache, no new Gemini call


def test_extract_over_limit_returns_429(monkeypatch):
    from backend.errors import ApiError

    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())

    def raise_limit(*a, **k):
        raise ApiError(429, "daily_limit_reached", "You've reached today's limit for this. Please try again tomorrow.")

    monkeypatch.setattr(main_module, "check_and_increment", raise_limit)

    response = client.post(
        "/api/extract",
        files={"file": ("x.png", make_png_bytes(size=(55, 66)), "image/png")},
    )
    assert response.status_code == 429
    assert response.json()["error_code"] == "daily_limit_reached"


def test_extract_rate_limit_from_gemini_returns_503(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())
    monkeypatch.setattr(main_module, "check_and_increment", lambda *a, **k: None)

    def raise_rate_limit(*a, **k):
        raise RateLimitError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(main_module, "extract_screenshot", raise_rate_limit)

    response = client.post(
        "/api/extract",
        files={"file": ("y.png", make_png_bytes(size=(77, 88)), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["error_code"] == "service_busy"


def _settings(**overrides):
    from backend.config import get_settings
    base = get_settings()
    return base.__class__(**{**base.__dict__, **overrides})
