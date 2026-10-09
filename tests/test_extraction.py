"""Tests for extraction/. All Gemini calls are mocked; no network calls."""
import io
from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors
from PIL import Image
from pydantic import ValidationError

from backend.config import get_settings
from extraction.extract import RateLimitError, _build_config, extract_screenshot
from extraction.image_prep import prepare_image
from extraction.schema import ExtractionResult, Trip

SETTINGS = get_settings()


def make_jpeg_bytes(size=(2000, 1000)) -> bytes:
    image = Image.new("RGB", size, (255, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")  # start as PNG to also prove format conversion
    return buf.getvalue()


def make_response(result: ExtractionResult, prompt_tokens=100, output_tokens=50, thinking_tokens=0):
    response = MagicMock()
    response.text = result.model_dump_json()
    response.usage_metadata = MagicMock(
        prompt_token_count=prompt_tokens,
        candidates_token_count=output_tokens,
        thoughts_token_count=thinking_tokens,
    )
    return response


VALID_RESULT = ExtractionResult(
    screen_type="trip_detail",
    trips=[Trip(base_pay=100.0, total_payout=100.0)],
    payout_summary=None,
    needs_review=False,
    notes=None,
)


# --- extraction/schema.py ---

def test_schema_accepts_minimal_valid_result():
    result = ExtractionResult(screen_type="other", needs_review=True)
    assert result.trips == []
    assert result.payout_summary is None


def test_schema_rejects_missing_required_fields():
    with pytest.raises(ValidationError):
        ExtractionResult(trips=[])  # missing screen_type and needs_review


def test_schema_rejects_negative_amount():
    with pytest.raises(ValidationError):
        Trip(base_pay=-5.0)


# --- extraction/image_prep.py ---

def test_prepare_image_resizes_to_max_side():
    raw = make_jpeg_bytes(size=(2000, 1000))
    out = prepare_image(raw, max_side_px=500, jpeg_quality=85)
    resized = Image.open(io.BytesIO(out))
    assert max(resized.size) == 500
    assert resized.format == "JPEG"


def test_prepare_image_leaves_small_image_unresized():
    raw = make_jpeg_bytes(size=(300, 200))
    out = prepare_image(raw, max_side_px=1280, jpeg_quality=85)
    resized = Image.open(io.BytesIO(out))
    assert resized.size == (300, 200)


def test_prepare_image_strips_metadata():
    image = Image.new("RGB", (100, 100), (0, 255, 0))
    buf = io.BytesIO()
    exif = image.getexif()
    exif[0x0131] = "some-software-tag"
    image.save(buf, format="JPEG", exif=exif)
    out = prepare_image(buf.getvalue(), max_side_px=1280, jpeg_quality=85)
    reopened = Image.open(io.BytesIO(out))
    assert not reopened.getexif()


# --- extraction/extract.py ---

def test_build_config_flash_lite_31_uses_minimal_thinking_and_temperature_zero():
    cfg = _build_config(SETTINGS, "gemini-3.1-flash-lite")
    assert str(cfg.thinking_config.thinking_level).endswith("MINIMAL")
    assert cfg.temperature == 0


def test_build_config_flash_lite_35_omits_temperature():
    cfg = _build_config(SETTINGS, "gemini-3.5-flash-lite")
    assert str(cfg.thinking_config.thinking_level).endswith("MINIMAL")
    assert cfg.temperature is None


def test_build_config_flash_38_uses_low_thinking_not_minimal():
    cfg = _build_config(SETTINGS, "gemini-3.8-flash")
    assert str(cfg.thinking_config.thinking_level).endswith("LOW")
    assert cfg.temperature == 0


def test_extract_screenshot_succeeds_on_first_call():
    client = MagicMock()
    client.models.generate_content.return_value = make_response(VALID_RESULT, prompt_tokens=120, output_tokens=60)

    outcome = extract_screenshot(client, SETTINGS, "gemini-3.5-flash-lite", b"fake-jpeg")

    assert outcome.calls_made == 1
    assert outcome.result.screen_type == "trip_detail"
    assert outcome.prompt_tokens == 120
    assert outcome.output_tokens == 60
    client.models.generate_content.assert_called_once()


def test_extract_screenshot_retries_once_on_invalid_json_then_succeeds():
    bad_response = MagicMock()
    bad_response.text = "not valid json"
    bad_response.usage_metadata = MagicMock(prompt_token_count=100, candidates_token_count=10, thoughts_token_count=0)
    good_response = make_response(VALID_RESULT)

    client = MagicMock()
    client.models.generate_content.side_effect = [bad_response, good_response]

    outcome = extract_screenshot(client, SETTINGS, "gemini-3.1-flash-lite", b"fake-jpeg")

    assert outcome.calls_made == 2
    assert outcome.result.screen_type == "trip_detail"
    assert client.models.generate_content.call_count == 2


def test_extract_screenshot_falls_back_to_needs_review_after_two_failures():
    bad_response = MagicMock()
    bad_response.text = "still not valid json"
    bad_response.usage_metadata = MagicMock(prompt_token_count=100, candidates_token_count=10, thoughts_token_count=0)

    client = MagicMock()
    client.models.generate_content.side_effect = [bad_response, bad_response]

    outcome = extract_screenshot(client, SETTINGS, "gemini-3.8-flash", b"fake-jpeg")

    assert outcome.calls_made == 2
    assert outcome.result.needs_review is True
    assert outcome.result.screen_type == "other"
    assert client.models.generate_content.call_count == 2


def test_extract_screenshot_never_retries_on_transient_network_error():
    client = MagicMock()
    client.models.generate_content.side_effect = TimeoutError("network timeout")

    outcome = extract_screenshot(client, SETTINGS, "gemini-3.5-flash-lite", b"fake-jpeg")

    assert outcome.calls_made == 1
    assert outcome.result.needs_review is True
    client.models.generate_content.assert_called_once()


def test_extract_screenshot_retries_429_with_pauses_then_raises(monkeypatch):
    sleeps = []
    monkeypatch.setattr("extraction.extract.time.sleep", lambda s: sleeps.append(s))

    error = genai_errors.ClientError(code=429, response_json={"error": {"message": "RESOURCE_EXHAUSTED"}})
    client = MagicMock()
    client.models.generate_content.side_effect = error

    with pytest.raises(RateLimitError):
        extract_screenshot(client, SETTINGS, "gemini-3.5-flash-lite", b"fake-jpeg")

    # 1 initial attempt + MAX_TRANSIENT_RETRIES (2) pauses-and-retries = 3 calls, 2 pauses
    assert client.models.generate_content.call_count == 3
    assert len(sleeps) == 2
    for s in sleeps:
        assert 1.0 <= s <= 3.0


def test_extract_screenshot_retries_5xx_server_error_the_same_way_as_429(monkeypatch):
    sleeps = []
    monkeypatch.setattr("extraction.extract.time.sleep", lambda s: sleeps.append(s))

    error = genai_errors.ServerError(code=503, response_json={"error": {"message": "UNAVAILABLE"}})
    client = MagicMock()
    client.models.generate_content.side_effect = error

    with pytest.raises(RateLimitError):
        extract_screenshot(client, SETTINGS, "gemini-3.1-flash-lite", b"fake-jpeg")

    assert client.models.generate_content.call_count == 3
    assert len(sleeps) == 2


def test_extract_screenshot_5xx_never_crashes_the_caller(monkeypatch):
    """backend/main.py catches RateLimitError and returns a friendly 503; this
    confirms extract_screenshot raises that same, catchable type for a 5xx,
    not an unhandled exception that would crash the request."""
    monkeypatch.setattr("extraction.extract.time.sleep", lambda s: None)
    error = genai_errors.ServerError(code=500, response_json={"error": {"message": "INTERNAL"}})
    client = MagicMock()
    client.models.generate_content.side_effect = error

    try:
        extract_screenshot(client, SETTINGS, "gemini-3.1-flash-lite", b"fake-jpeg")
        assert False, "expected RateLimitError"
    except RateLimitError:
        pass  # exactly the catchable, documented outcome -- never a crash
