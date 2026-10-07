"""Calls Gemini to turn one prepared screenshot into an ExtractionResult.

Exactly one call per screenshot, plus at most one retry on invalid output,
then needs_review=True (REQUIREMENTS.md sections 6 and 19). Structured JSON
output against ExtractionResult. Gemini never does arithmetic: this module
only ever returns what the model copied off the screen.
"""
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
            result = ExtractionResult.model_validate_json(response.text)
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
