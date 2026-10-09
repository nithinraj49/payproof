"""Reads every environment variable listed in REQUIREMENTS.md section 20.

Values are read lazily from os.environ (via python-dotenv in local dev) so that
importing this module never requires a real .env file to exist (tests run
without one).
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


@dataclass(frozen=True)
class Settings:
    project_id: str
    region: str
    vertex_location: str
    gemini_backend: str
    gemini_api_key: str
    extraction_model: str
    explain_model: str
    gemini_timeout_seconds: int
    image_max_side_px: int
    image_jpeg_quality: int
    max_upload_mb: int
    extraction_max_output_tokens: int
    answer_max_output_tokens: int
    limit_extractions_per_user_per_day: int
    limit_questions_per_user_per_day: int
    limit_global_gemini_calls_per_day: int
    quality_min_short_side_px: int
    quality_min_sharpness: float
    quality_min_contrast: float
    quality_min_brightness: float
    quality_max_brightness: float


def _running_on_cloud_run() -> bool:
    # Cloud Run sets K_SERVICE automatically on every revision; nothing else
    # does, so its presence is a reliable "we are deployed" signal.
    return bool(os.environ.get("K_SERVICE"))


def _validate_for_cloud_run(settings: "Settings") -> None:
    """On Cloud Run, refuse to start with a configuration that would silently
    fall back to the aistudio backend (empty GEMINI_API_KEY there) instead of
    Vertex AI (REQUIREMENTS.md section 0: the deployed app must use Vertex
    AI). Local/dev runs (no K_SERVICE) keep the aistudio default untouched.
    The error message never includes any secret or key value.
    """
    if not _running_on_cloud_run():
        return
    problems = []
    if settings.gemini_backend != "vertex":
        problems.append(f'GEMINI_BACKEND must be "vertex" on Cloud Run (got {settings.gemini_backend!r})')
    if not settings.project_id:
        problems.append("PROJECT_ID must be set")
    if not settings.vertex_location:
        problems.append("VERTEX_LOCATION must be set")
    if problems:
        raise RuntimeError(
            "Refusing to start on Cloud Run with an invalid configuration: " + "; ".join(problems)
        )


def get_settings() -> Settings:
    settings = Settings(
        project_id=_env_str("PROJECT_ID", "payproof-nithin-2026"),
        region=_env_str("REGION", "asia-south1"),
        vertex_location=_env_str("VERTEX_LOCATION", "global"),
        gemini_backend=_env_str("GEMINI_BACKEND", "aistudio"),
        gemini_api_key=_env_str("GEMINI_API_KEY", ""),
        extraction_model=_env_str("EXTRACTION_MODEL", "gemini-3.5-flash-lite"),
        explain_model=_env_str("EXPLAIN_MODEL", "gemini-3.5-flash-lite"),
        gemini_timeout_seconds=_env_int("GEMINI_TIMEOUT_SECONDS", 30),
        image_max_side_px=_env_int("IMAGE_MAX_SIDE_PX", 1280),
        image_jpeg_quality=_env_int("IMAGE_JPEG_QUALITY", 85),
        max_upload_mb=_env_int("MAX_UPLOAD_MB", 8),
        extraction_max_output_tokens=_env_int("EXTRACTION_MAX_OUTPUT_TOKENS", 1500),
        answer_max_output_tokens=_env_int("ANSWER_MAX_OUTPUT_TOKENS", 400),
        limit_extractions_per_user_per_day=_env_int("LIMIT_EXTRACTIONS_PER_USER_PER_DAY", 12),
        limit_questions_per_user_per_day=_env_int("LIMIT_QUESTIONS_PER_USER_PER_DAY", 25),
        limit_global_gemini_calls_per_day=_env_int("LIMIT_GLOBAL_GEMINI_CALLS_PER_DAY", 400),
        # Tuned empirically on the 30 simulated standard images (none blocked); NOT
        # validated on real screenshots. See extraction/image_quality.py and PROGRESS.md.
        quality_min_short_side_px=_env_int("QUALITY_MIN_SHORT_SIDE_PX", 300),
        quality_min_sharpness=_env_float("QUALITY_MIN_SHARPNESS", 3.9),
        quality_min_contrast=_env_float("QUALITY_MIN_CONTRAST", 10.0),
        quality_min_brightness=_env_float("QUALITY_MIN_BRIGHTNESS", 15.0),
        quality_max_brightness=_env_float("QUALITY_MAX_BRIGHTNESS", 254.0),
    )
    _validate_for_cloud_run(settings)
    return settings
