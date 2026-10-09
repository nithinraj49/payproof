import logging

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.exceptions import HTTPException

from backend.auth import require_user_id
from backend.config import get_settings
from backend.errors import ApiError, api_error_handler, http_exception_handler
from backend.extraction_cache import get_cached, hash_image, set_cached
from backend.gemini_client import get_client
from backend.sample_cache import get_cached_sample, set_cached_sample
from backend.usage_limits import check_and_increment
from extraction.extract import RateLimitError, extract_screenshot
from extraction.image_prep import prepare_image
from extraction.image_quality import QUALITY_MESSAGES, check_image_quality
from extraction.schema import ExtractionResult

logger = logging.getLogger("payproof.api")

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}

# Calling this at import time (not just inside each request handler) means an
# invalid Cloud Run configuration raises before uvicorn finishes starting, so
# the container never comes up and never receives traffic.
get_settings()

app = FastAPI(title="PayProof API")
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/whoami")
def whoami(user_id: str = Depends(require_user_id)):
    return {"user_id": user_id}


@app.post("/api/extract")
async def extract(
    user_id: str = Depends(require_user_id),
    file: UploadFile = File(...),
    is_sample: bool = Form(False),
):
    settings = get_settings()

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(415, "unsupported_file_type", "Please upload a PNG, JPEG or WebP image.")

    raw = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise ApiError(413, "file_too_large", f"That image is larger than {settings.max_upload_mb} MB. Please upload a smaller screenshot.")

    try:
        jpeg_bytes = prepare_image(raw, settings.image_max_side_px, settings.image_jpeg_quality)
    except Exception:
        raise ApiError(400, "unreadable_image", "Could not read that image. Please upload a clear screenshot.")

    # Deterministic quality gate, no Gemini call: a failing image costs nothing
    # and never reaches the API or the usage-limit counters.
    quality = check_image_quality(
        jpeg_bytes,
        settings.quality_min_short_side_px,
        settings.quality_min_sharpness,
        settings.quality_min_contrast,
        settings.quality_min_brightness,
        settings.quality_max_brightness,
    )
    if not quality.passed:
        logger.info("extraction uid=%s rejected by quality gate reason=%s", user_id, quality.reason)
        result = ExtractionResult(
            screen_type="other", trips=[], payout_summary=None,
            needs_review=True, notes=QUALITY_MESSAGES[quality.reason],
        )
        return result.model_dump()

    image_hash = hash_image(jpeg_bytes)

    if is_sample:
        # Shared, persistent cache across all visitors (never user uploads):
        # REQUIREMENTS.md section 19 rule 5. A cache hit costs no Gemini call
        # and no usage-limit charge -- the whole point of the sample button.
        cached_sample = get_cached_sample(image_hash)
        if cached_sample is not None:
            return cached_sample.model_dump()
    else:
        cached = get_cached(image_hash)
        if cached is not None:
            return cached.model_dump()
        check_and_increment(user_id, "extractions", settings.limit_extractions_per_user_per_day, settings.limit_global_gemini_calls_per_day)

    client = get_client(settings)
    try:
        outcome = extract_screenshot(client, settings, settings.extraction_model, jpeg_bytes)
    except RateLimitError:
        raise ApiError(503, "service_busy", "PayProof is busy right now. Please try again in a minute.")

    logger.info(
        "extraction uid=%s model=%s is_sample=%s calls_made=%s prompt_tokens=%s output_tokens=%s thinking_tokens=%s",
        user_id, settings.extraction_model, is_sample, outcome.calls_made,
        outcome.prompt_tokens, outcome.output_tokens, outcome.thinking_tokens,
    )

    if is_sample:
        set_cached_sample(image_hash, outcome.result)
    else:
        set_cached(image_hash, outcome.result)
    return outcome.result.model_dump()
