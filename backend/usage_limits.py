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


def check_limits(user_count: int, global_count: int, user_limit: int, global_limit: int) -> None:
    """Pure limit check, no I/O: easy to unit test without a Firestore emulator."""
    if user_count >= user_limit:
        raise ApiError(429, "daily_limit_reached", "You've reached today's limit for this. Please try again tomorrow.")
    if global_count >= global_limit:
        raise ApiError(503, "service_busy", "PayProof has reached its usage limit for today. Please try again tomorrow.")


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
        user_count = (user_snap.get(kind) if user_snap.exists else 0) or 0
        global_count = (global_snap.get("gemini_calls") if global_snap.exists else 0) or 0

        check_limits(user_count, global_count, user_limit, global_limit)

        transaction.set(user_ref, {kind: user_count + 1}, merge=True)
        transaction.set(global_ref, {"gemini_calls": global_count + 1}, merge=True)

    _run(transaction)
