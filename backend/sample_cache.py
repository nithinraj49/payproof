"""Shared cache for the curated SAMPLE images only (simulated, never user
uploads) -- REQUIREMENTS.md section 19 rule 5. Persisted in Firestore (not
per-process memory) so every visitor after the very first one who taps "Try
with sample screenshots" costs zero Gemini calls, while the real extraction
code path still runs end to end for the first visitor.
"""
from functools import lru_cache
from typing import Optional

import firebase_admin
from firebase_admin import firestore

from extraction.schema import ExtractionResult

if not firebase_admin._apps:
    firebase_admin.initialize_app()

SAMPLE_CACHE_COLLECTION = "sample_cache"


@lru_cache
def get_db():
    return firestore.client()


def get_cached_sample(image_hash: str, db=None) -> Optional[ExtractionResult]:
    db = db or get_db()
    doc = db.collection(SAMPLE_CACHE_COLLECTION).document(image_hash).get()
    if not doc.exists:
        return None
    return ExtractionResult.model_validate(doc.to_dict()["result"])


def set_cached_sample(image_hash: str, result: ExtractionResult, db=None) -> None:
    db = db or get_db()
    db.collection(SAMPLE_CACHE_COLLECTION).document(image_hash).set({"result": result.model_dump()})
