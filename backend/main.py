import logging

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.exceptions import HTTPException

from backend.auth import require_user_id
from backend.config import get_settings
from backend.errors import ApiError, api_error_handler, http_exception_handler
from backend.extraction_cache import get_cached, hash_image, set_cached
from backend.gemini_client import get_client
from backend.usage_limits import check_and_increment
from extraction.extract import RateLimitError, extract_screenshot
from extraction.image_prep import prepare_image

logger = logging.getLogger("payproof.api")

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}

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
async def extract(user_id: str = Depends(require_user_id), file: UploadFile = File(...)):
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

    image_hash = hash_image(jpeg_bytes)
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
        "extraction uid=%s model=%s calls_made=%s prompt_tokens=%s output_tokens=%s thinking_tokens=%s",
        user_id, settings.extraction_model, outcome.calls_made,
        outcome.prompt_tokens, outcome.output_tokens, outcome.thinking_tokens,
    )

    set_cached(image_hash, outcome.result)
    return outcome.result.model_dump()
