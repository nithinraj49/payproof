"""Tests for extraction/. All Gemini calls are mocked; no network calls."""
import io
import json
import logging
from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors
from PIL import Image
from pydantic import ValidationError

from backend.config import get_settings
from extraction.extract import RateLimitError, _build_config, _estimated_cost_usd, extract_screenshot
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


# --- extraction/extract.py: Gemini-call JSON log line ---
#
# The production fix attaches a StreamHandler(sys.stdout) directly to the
# "payproof.gemini_calls" logger (extraction/extract.py), with propagate=False,
# so the line reaches stdout (and so Cloud Run logs) independent of whatever
# the root logger is or isn't configured with -- that's the actual bug being
# fixed here. For the test, attach caplog's own handler directly to that same
# logger (bypassing propagation and OS-level stdout capture entirely, which
# has flush-timing quirks under pytest on Windows) to inspect the real
# LogRecords emitted.
GEMINI_CALL_LOGGER = logging.getLogger("payproof.gemini_calls")


@pytest.fixture
def gemini_call_records(caplog):
    caplog.set_level(logging.INFO, logger="payproof.gemini_calls")
    GEMINI_CALL_LOGGER.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        GEMINI_CALL_LOGGER.removeHandler(caplog.handler)


def _records(caplog) -> list:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "payproof.gemini_calls"]


def test_successful_call_logs_one_json_line_with_required_fields(gemini_call_records):
    client = MagicMock()
    client.models.generate_content.return_value = make_response(VALID_RESULT, prompt_tokens=120, output_tokens=60, thinking_tokens=5)

    extract_screenshot(client, SETTINGS, "gemini-3.1-flash-lite", b"fake-jpeg")

    records = _records(gemini_call_records)
    assert len(records) == 1
    record = records[0]
    assert set(record.keys()) == {
        "timestamp", "endpoint", "model", "prompt_tokens", "output_tokens",
        "thinking_tokens", "outcome", "estimated_cost_usd",
    }
    assert record["endpoint"] == "extract"
    assert record["model"] == "gemini-3.1-flash-lite"
    assert record["prompt_tokens"] == 120
    assert record["output_tokens"] == 65  # candidates (60) + thinking (5), per _call_once
    assert record["thinking_tokens"] == 5
    assert record["outcome"] == "ok"
    assert record["estimated_cost_usd"] > 0
    # No image bytes, no extracted field values, no user id anywhere in the line.
    assert "fake-jpeg" not in json.dumps(record)
    assert "trip_detail" not in json.dumps(record)
    assert "100.0" not in json.dumps(record)


def test_call_failed_logs_zero_tokens_and_that_outcome(gemini_call_records):
    client = MagicMock()
    client.models.generate_content.side_effect = TimeoutError("network timeout")

    extract_screenshot(client, SETTINGS, "gemini-3.5-flash-lite", b"fake-jpeg")

    records = _records(gemini_call_records)
    assert len(records) == 1
    assert records[0]["outcome"] == "call_failed"
    assert records[0]["prompt_tokens"] == 0
    assert records[0]["output_tokens"] == 0
    assert records[0]["estimated_cost_usd"] == 0.0


def test_rate_limited_logs_that_outcome(gemini_call_records, monkeypatch):
    monkeypatch.setattr("extraction.extract.time.sleep", lambda s: None)
    error = genai_errors.ClientError(code=429, response_json={"error": {"message": "RESOURCE_EXHAUSTED"}})
    client = MagicMock()
    client.models.generate_content.side_effect = error

    with pytest.raises(RateLimitError):
        extract_screenshot(client, SETTINGS, "gemini-3.5-flash-lite", b"fake-jpeg")

    records = _records(gemini_call_records)
    assert len(records) == 1
    assert records[0]["outcome"] == "rate_limited"
    assert records[0]["prompt_tokens"] == 0


def test_invalid_output_then_retry_logs_two_lines(gemini_call_records):
    bad_response = MagicMock()
    bad_response.text = "not valid json"
    bad_response.usage_metadata = MagicMock(prompt_token_count=100, candidates_token_count=10, thoughts_token_count=0)
    good_response = make_response(VALID_RESULT, prompt_tokens=90, output_tokens=40)

    client = MagicMock()
    client.models.generate_content.side_effect = [bad_response, good_response]

    extract_screenshot(client, SETTINGS, "gemini-3.1-flash-lite", b"fake-jpeg")

    records = _records(gemini_call_records)
    assert len(records) == 2
    assert records[0]["outcome"] == "invalid_output"
    assert records[0]["prompt_tokens"] == 100
    assert records[1]["outcome"] == "ok"
    assert records[1]["prompt_tokens"] == 90


def test_estimated_cost_usd_matches_known_pricing():
    # gemini-3.1-flash-lite: $0.25/1M input, $1.50/1M output (unverified, see PROGRESS.md)
    cost = _estimated_cost_usd("gemini-3.1-flash-lite", prompt_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(0.25 + 1.50)


def test_estimated_cost_usd_unknown_model_is_zero():
    assert _estimated_cost_usd("some-future-model", 1000, 1000) == 0.0
