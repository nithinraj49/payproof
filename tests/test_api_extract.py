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


def make_png_bytes(size=(320, 320)) -> bytes:
    # A noisy checkerboard, not a flat color: must pass the quality gate
    # (extraction/image_quality.py) so these tests exercise what they're
    # meant to (the extraction/cache/limits path), not the quality gate
    # itself (see tests/test_image_quality.py for that).
    image = Image.new("RGB", size, (130, 130, 130))
    pixels = image.load()
    for x in range(0, size[0], 4):
        for y in range(0, size[1], 4):
            pixels[x, y] = (255, 255, 255) if (x + y) % 8 == 0 else (0, 0, 0)
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
        files={"file": ("trip.png", make_png_bytes(size=(320, 340)), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["screen_type"] == "trip_detail"
    extract_mock.assert_called_once()
    assert len(check_calls) == 1


def test_extract_blocks_low_quality_image_before_any_gemini_call(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    extract_mock = MagicMock()
    monkeypatch.setattr(main_module, "extract_screenshot", extract_mock)
    check_calls = []
    monkeypatch.setattr(main_module, "check_and_increment", lambda *a, **k: check_calls.append(a))

    # A flat, uniform-color image: no edges, no contrast -> fails the quality gate.
    flat_image = Image.new("RGB", (320, 320), (128, 128, 128))
    buf = io.BytesIO()
    flat_image.save(buf, format="PNG")

    response = client.post("/api/extract", files={"file": ("flat.png", buf.getvalue(), "image/png")})
    assert response.status_code == 200
    body = response.json()
    assert body["needs_review"] is True
    assert body["screen_type"] == "other"
    extract_mock.assert_not_called()
    assert len(check_calls) == 0  # no usage-limit charge for a gate rejection


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
        files={"file": ("x.png", make_png_bytes(size=(320, 350)), "image/png")},
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
        files={"file": ("y.png", make_png_bytes(size=(320, 360)), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["error_code"] == "service_busy"


def test_extract_sample_image_skips_usage_limit_and_uses_shared_cache(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_client", lambda s: MagicMock())

    check_calls = []
    monkeypatch.setattr(main_module, "check_and_increment", lambda *a, **k: check_calls.append(a))

    sample_cache = {}
    monkeypatch.setattr(main_module, "get_cached_sample", lambda h: sample_cache.get(h))
    monkeypatch.setattr(main_module, "set_cached_sample", lambda h, r: sample_cache.__setitem__(h, r))

    result = ExtractionResult(screen_type="order_offer", needs_review=False)
    outcome = ExtractionCallResult(result=result, calls_made=1, prompt_tokens=100, output_tokens=50, thinking_tokens=0)
    extract_mock = MagicMock(return_value=outcome)
    monkeypatch.setattr(main_module, "extract_screenshot", extract_mock)

    image_bytes = make_png_bytes(size=(340, 340))
    r1 = client.post("/api/extract", data={"is_sample": "true"}, files={"file": ("s.png", image_bytes, "image/png")})
    r2 = client.post("/api/extract", data={"is_sample": "true"}, files={"file": ("s.png", image_bytes, "image/png")})

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    extract_mock.assert_called_once()  # second call served from the shared sample cache
    assert len(check_calls) == 0  # usage limit never charged for a sample extraction


def _settings(**overrides):
    from backend.config import get_settings
    base = get_settings()
    return base.__class__(**{**base.__dict__, **overrides})
