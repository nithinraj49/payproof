"""Single entry point for every Gemini call, switching on GEMINI_BACKEND.

Phase 1: skeleton only, no Gemini call is made yet. extraction/ and backend/qa.py
(Phases 2 and 4) will call get_client() and never construct a genai.Client directly,
so every Gemini call in the app goes through this one module.
"""
from functools import lru_cache

from google import genai

from backend.config import Settings, get_settings


@lru_cache
def get_client(settings: Settings | None = None) -> genai.Client:
    settings = settings or get_settings()
    if settings.gemini_backend == "vertex":
        return genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.vertex_location,
        )
    if settings.gemini_backend == "aistudio":
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_BACKEND=aistudio requires GEMINI_API_KEY to be set in .env "
                "(local, simulated images only)."
            )
        return genai.Client(api_key=settings.gemini_api_key)
    raise ValueError(f"Unknown GEMINI_BACKEND: {settings.gemini_backend!r}")
