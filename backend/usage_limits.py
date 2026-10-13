"""Atomic per-user and global Gemini usage counters (REQUIREMENTS.md sections
10 and 19 rule 7). Firestore is the source of truth so the limit holds across
Cloud Run instances and restarts.
"""
import datetime
from functools import lru_cache
from typing import Optional

import firebase_admin
from firebase_admin import firestore

from backend.errors import ApiError

if not firebase_admin._apps:
    firebase_admin.initialize_app()


@lru_cache
def get_db():
    return firestore.client()


def _today() -> str:
    return datetime.date.today().isoformat()


def _field_count(snapshot, field: str) -> int:
    """Safe equivalent of `snapshot.get(field) or 0`.

    DocumentSnapshot.get(field_path) raises KeyError when the document
    exists but that particular field doesn't -- unlike dict.get(), it does
    NOT default to None. That is a real bug found live: a visitor whose
    usage doc already had "extractions" (from an earlier /api/extract call
    the same day) got an uncaught KeyError, and therefore a bare 500, on
    their first /api/ask of the day, because "questions" wasn't in the
    document yet. Going through to_dict() first sidesteps the special
    field-path lookup entirely.
    """
    return (snapshot.to_dict() or {}).get(field, 0) or 0


def check_limits(user_count: int, global_count: int, user_limit: int, global_limit: int) -> None:
    """Pure limit check, no I/O: easy to unit test without a Firestore emulator."""
    if user_count >= user_limit:
        raise ApiError(429, "daily_limit_reached", "You've reached today's limit for this. Please try again tomorrow.")
    if global_count >= global_limit:
        raise ApiError(503, "service_busy", "PayProof has reached its usage limit for today. Please try again tomorrow.")


def check_global_limit_only(
    global_limit: int, db: Optional["firestore.Client"] = None, day: Optional[str] = None,
) -> None:
    """For a verified curated-sample extraction only (backend/main.py checks
    the server-computed image hash against backend.sample_images before ever
    calling this): never charged to a visitor's per-user daily limit, since
    the whole point of the shared sample cache is that trying the demo costs
    a visitor nothing (REQUIREMENTS.md section 19 rule 5). But the GLOBAL cap
    must still apply to every real Gemini call, including the first visitor
    who populates a sample image's cache entry -- so this still increments
    the same `usage_global/{day}` counter check_and_increment uses, just
    without touching any per-user document.
    """
    db = db or get_db()
    day = day or _today()
    global_ref = db.collection("usage_global").document(day)
    transaction = db.transaction()

    @firestore.transactional
    def _run(transaction):
        global_snap = global_ref.get(transaction=transaction)
        global_count = _field_count(global_snap, "gemini_calls")
        if global_count >= global_limit:
            raise ApiError(503, "service_busy", "PayProof has reached its usage limit for today. Please try again tomorrow.")
        transaction.set(global_ref, {"gemini_calls": global_count + 1}, merge=True)

    _run(transaction)


def check_and_increment(
    uid: str, kind: str, user_limit: int, global_limit: int,
    db: Optional["firestore.Client"] = None, day: Optional[str] = None,
) -> None:
    """kind is "extractions" or "questions". Raises ApiError if either limit is
    already reached; otherwise atomically increments both counters for today.
    `day` defaults to today's date; eval/check_firestore_usage_limits.py passes
    an obviously-fake day so its throwaway test never touches a real counter.
    """
    db = db or get_db()
    day = day or _today()
    user_ref = db.collection("users").document(uid).collection("usage").document(day)
    global_ref = db.collection("usage_global").document(day)
    transaction = db.transaction()

    @firestore.transactional
    def _run(transaction):
        user_snap = user_ref.get(transaction=transaction)
        global_snap = global_ref.get(transaction=transaction)
        user_count = _field_count(user_snap, kind)
        global_count = _field_count(global_snap, "gemini_calls")

        check_limits(user_count, global_count, user_limit, global_limit)

        transaction.set(user_ref, {kind: user_count + 1}, merge=True)
        transaction.set(global_ref, {"gemini_calls": global_count + 1}, merge=True)

    _run(transaction)
