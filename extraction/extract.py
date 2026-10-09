"""Calls Gemini to turn one prepared screenshot into an ExtractionResult.

Exactly one call per screenshot, plus at most one retry on invalid output,
then needs_review=True (REQUIREMENTS.md sections 6 and 19). Structured JSON
output against ExtractionResult. Gemini never does arithmetic: this module
only ever returns what the model copied off the screen, then applies
deterministic, code-only safeguards (no extra Gemini calls) below.
"""
import datetime
import json as jsonlib
import logging
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from backend.config import Settings
from extraction.prompt import SYSTEM_PROMPT
from extraction.schema import ExtractionResult

logger = logging.getLogger("payproof.extraction")

# --- Deterministic post-processing safeguards (plain code, no Gemini call) ---
# Found necessary after the Phase 2 hard-tier evaluation: the model sometimes
# flags a field as low-confidence (or the reconciliation implies it should be)
# but still returns a guessed, wrong value instead of null.
RECONCILIATION_TOLERANCE = 0.5
PLAUSIBLE_DATE_MIN = datetime.date(2020, 1, 1)

# --- low_confidence_fields label normalizer ---
# extraction/schema.py now constrains low_confidence_fields to a Literal of the
# real field names, so a compliant Gemini response_schema call can no longer
# emit a label like "Base pay". This normalizer is a backstop: for any output
# produced before that change, or from a model that doesn't fully comply, it
# maps common human labels to the real field name, and treats anything it
# can't recognize as a reason to distrust the whole record.
TRIP_VALID_FIELDS = {
    "trip_date", "order_id", "order_type", "base_pay", "incentive", "tip",
    "total_payout", "distance_km", "duration_min",
}
TRIP_LABEL_ALIASES = {
    "date": "trip_date", "trip date": "trip_date",
    "order id": "order_id", "order": "order_id",
    "order type": "order_type", "type": "order_type",
    "base pay": "base_pay", "base": "base_pay",
    "incentive": "incentive",
    "tip": "tip",
    "total payout": "total_payout", "total": "total_payout", "payout": "total_payout",
    "distance": "distance_km", "distance km": "distance_km", "km": "distance_km",
    "duration": "duration_min", "minutes": "duration_min", "duration min": "duration_min",
}
PAYOUT_VALID_FIELDS = {"period_label", "period_start", "period_end", "total_credited", "credited_on"}
PAYOUT_LABEL_ALIASES = {
    "period label": "period_label", "period": "period_label",
    "period start": "period_start", "start": "period_start",
    "period end": "period_end", "end": "period_end",
    "total credited": "total_credited", "total": "total_credited", "credited": "total_credited",
    "credited on": "credited_on", "date": "credited_on",
}


def _normalize_labels(low_confidence_fields, valid_fields: set, aliases: dict) -> tuple:
    """Returns (normalized_sorted_list, any_unrecognized)."""
    normalized = set()
    unrecognized = False
    for label in low_confidence_fields or []:
        key = str(label).strip().lower()
        if key in valid_fields:
            normalized.add(key)
        elif key in aliases:
            normalized.add(aliases[key])
        else:
            unrecognized = True
    return sorted(normalized), unrecognized


def normalize_low_confidence_labels(data: dict) -> dict:
    """Operates on the raw parsed-JSON dict, before Pydantic validation (a
    non-canonical label would otherwise fail the Literal-constrained schema
    outright). Any unrecognized label is treated conservatively: every money
    field on that record is added to low_confidence_fields (apply_deterministic_
    safeguards then nulls them) and needs_review is forced true.
    """
    forced_review = False
    for trip in data.get("trips") or []:
        normalized, unrecognized = _normalize_labels(trip.get("low_confidence_fields"), TRIP_VALID_FIELDS, TRIP_LABEL_ALIASES)
        if unrecognized:
            normalized = sorted(set(normalized) | set(TRIP_MONEY_FIELDS))
            forced_review = True
        trip["low_confidence_fields"] = normalized

    summary = data.get("payout_summary")
    if summary:
        normalized, unrecognized = _normalize_labels(summary.get("low_confidence_fields"), PAYOUT_VALID_FIELDS, PAYOUT_LABEL_ALIASES)
        if unrecognized:
            normalized = sorted(set(normalized) | {"total_credited"})
            forced_review = True
        summary["low_confidence_fields"] = normalized

    if forced_review:
        data["needs_review"] = True
    return data
TRIP_MONEY_FIELDS = ["base_pay", "incentive", "tip", "total_payout"]


def _is_plausible_date(date_str: Optional[str]) -> bool:
    if not date_str:
        return False
    try:
        d = datetime.date.fromisoformat(date_str)
    except ValueError:
        return False
    return PLAUSIBLE_DATE_MIN <= d <= datetime.date.today()


def _safeguard_trip(trip: dict) -> dict:
    low_confidence = set(trip.get("low_confidence_fields") or [])

    # (b) reconciliation, computed from the values as the model returned them,
    # before any nulling: if it doesn't add up, the money fields are suspect
    # even if the model didn't say so itself.
    if trip.get("total_payout") is not None:
        parts = (
            (trip.get("base_pay") or 0)
            + (trip.get("incentive") or 0)
            + (trip.get("tip") or 0)
            - sum(d["amount"] for d in trip.get("deductions") or [])
        )
        if abs(parts - trip["total_payout"]) > RECONCILIATION_TOLERANCE:
            low_confidence.update(TRIP_MONEY_FIELDS)

    # (a) any field named low-confidence (originally, or just added by the
    # reconciliation check above) becomes null.
    for field in low_confidence:
        if trip.get(field) is not None:
            trip[field] = None
    trip["low_confidence_fields"] = sorted(low_confidence)

    # (c) an implausible date becomes null.
    if trip.get("trip_date") is not None and not _is_plausible_date(trip["trip_date"]):
        trip["trip_date"] = None

    # (d) zero or negative distance/duration becomes null (not a real trip value).
    # Note: extraction/schema.py already enforces ge=0 on both fields, so a
    # genuinely negative value can never reach here (it fails schema validation
    # first, triggering the one allowed retry). Zero is schema-valid but still
    # not a plausible real trip, so it's handled here.
    if trip.get("distance_km") is not None and trip["distance_km"] <= 0:
        trip["distance_km"] = None
    if trip.get("duration_min") is not None and trip["duration_min"] <= 0:
        trip["duration_min"] = None

    return trip


def apply_deterministic_safeguards(result: ExtractionResult) -> ExtractionResult:
    """Runs rules (a)-(d) on every trip in the result. Scoped to Trip fields only
    (base_pay/incentive/tip/deductions/total_payout, trip_date, distance_km,
    duration_min) — PayoutSummary has no equivalent distance/duration fields
    and a different reconciliation formula, so it is left untouched here.
    Sets needs_review=True on the overall result whenever any field actually
    changed (was non-null and became null), even if the model hadn't already
    flagged it.
    """
    data = result.model_dump()
    changed = False

    for trip in data["trips"]:
        before = dict(trip)
        _safeguard_trip(trip)
        if any(trip.get(f) != before.get(f) for f in TRIP_MONEY_FIELDS + ["trip_date", "distance_km", "duration_min"]):
            changed = True

    if changed:
        data["needs_review"] = True

    return ExtractionResult.model_validate(data)


class RateLimitError(RuntimeError):
    """Raised instead of retrying/falling back, so callers can stop immediately
    instead of hammering a rate-limited API (REQUIREMENTS.md section 19: never loop)."""


def _is_rate_limit(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429:
        return True
    message = str(exc).lower()
    return "resource_exhausted" in message or "rate limit" in message or "quota" in message

# gemini-3.1-flash-lite and gemini-3.5-flash-lite: MINIMAL is the lowest level.
# gemini-3.8-flash: MINIMAL is rejected by the API (validation error); LOW is its lowest level.
# Checked against the current model docs (docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/*), Oct 2026.
THINKING_LEVEL_BY_MODEL = {
    "gemini-3.1-flash-lite": "MINIMAL",
    "gemini-3.5-flash-lite": "MINIMAL",
    "gemini-3.8-flash": "LOW",
}

# gemini-3.5-flash-lite ignores custom temperature/top-K/top-P entirely (current docs:
# "Custom values for parameters like temperature, top-K, and top-P aren't supported.
# If you set a custom value for these parameters, that value will be ignored."), so we
# don't set it there. gemini-3.1-flash-lite and gemini-3.8-flash both support temperature.
MODELS_SUPPORTING_TEMPERATURE = {"gemini-3.1-flash-lite", "gemini-3.8-flash"}


@dataclass
class ExtractionCallResult:
    result: ExtractionResult
    calls_made: int
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int


def _build_config(settings: Settings, model: str) -> types.GenerateContentConfig:
    kwargs = dict(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ExtractionResult,
        max_output_tokens=settings.extraction_max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL_BY_MODEL.get(model, "MINIMAL")),
        http_options=types.HttpOptions(timeout=settings.gemini_timeout_seconds * 1000),
    )
    if model in MODELS_SUPPORTING_TEMPERATURE:
        kwargs["temperature"] = 0
    return types.GenerateContentConfig(**kwargs)


def _call_once(client: genai.Client, settings: Settings, model: str, jpeg_bytes: bytes):
    image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
    response = client.models.generate_content(
        model=model,
        contents=[image_part, "Extract this screen."],
        config=_build_config(settings, model),
    )
    usage = response.usage_metadata
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    thinking_tokens = getattr(usage, "thoughts_token_count", 0) or 0
    output_tokens = (getattr(usage, "candidates_token_count", 0) or 0) + thinking_tokens
    return response, prompt_tokens, output_tokens, thinking_tokens


def _needs_review_fallback(note: str) -> ExtractionResult:
    return ExtractionResult(
        screen_type="other",
        trips=[],
        payout_summary=None,
        needs_review=True,
        notes=note,
    )


def extract_screenshot(client: genai.Client, settings: Settings, model: str, jpeg_bytes: bytes) -> ExtractionCallResult:
    """Exactly one call, at most one retry on invalid output, then a safe fallback."""
    total_prompt_tokens = 0
    total_output_tokens = 0
    total_thinking_tokens = 0

    for attempt in range(2):  # one call + at most one retry
        try:
            response, prompt_tokens, output_tokens, thinking_tokens = _call_once(client, settings, model, jpeg_bytes)
        except Exception as exc:  # network error, timeout, API error: no further retry here
            if _is_rate_limit(exc):
                raise RateLimitError(str(exc)) from exc
            logger.warning("Gemini call failed (model=%s, attempt=%s): %s", model, attempt, type(exc).__name__)
            return ExtractionCallResult(
                result=_needs_review_fallback("Could not read this screenshot right now. Please try again."),
                calls_made=attempt + 1,
                prompt_tokens=total_prompt_tokens,
                output_tokens=total_output_tokens,
                thinking_tokens=total_thinking_tokens,
            )

        total_prompt_tokens += prompt_tokens
        total_output_tokens += output_tokens
        total_thinking_tokens += thinking_tokens

        try:
            raw_data = jsonlib.loads(response.text)
            raw_data = normalize_low_confidence_labels(raw_data)
            result = ExtractionResult.model_validate(raw_data)
            result = apply_deterministic_safeguards(result)
            return ExtractionCallResult(
                result=result,
                calls_made=attempt + 1,
                prompt_tokens=total_prompt_tokens,
                output_tokens=total_output_tokens,
                thinking_tokens=total_thinking_tokens,
            )
        except (ValidationError, ValueError) as exc:
            logger.warning("Invalid extraction output (model=%s, attempt=%s): %s", model, attempt, type(exc).__name__)
            continue  # one retry allowed

    return ExtractionCallResult(
        result=_needs_review_fallback("Could not read this screenshot reliably. Please try a clearer photo."),
        calls_made=2,
        prompt_tokens=total_prompt_tokens,
        output_tokens=total_output_tokens,
        thinking_tokens=total_thinking_tokens,
    )
