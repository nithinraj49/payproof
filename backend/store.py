"""Firestore storage for confirmed trip, week and cost data (REQUIREMENTS.md
sections 4.2 and 10).

Documents live under users/{uid}/trips/, users/{uid}/weeks/ and
users/{uid}/costs/current. The user id always comes from the verified
Firebase token; it is never taken from a request path or body.

No images are ever stored here. Per section 11: never store names, phone
numbers or addresses (those fields are not extracted; enforced in extraction/).
"""
import datetime
import uuid
from functools import lru_cache
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import firestore

from backend.errors import ApiError

if not firebase_admin._apps:
    firebase_admin.initialize_app()


@lru_cache
def _db():
    return firestore.client()


def _user_ref(uid: str):
    return _db().collection("users").document(uid)


# ---------------------------------------------------------------------------
# Trips
# ---------------------------------------------------------------------------

def save_trips(uid: str, trip_rows: List[Dict[str, Any]]) -> List[str]:
    """Write a list of confirmed trip dicts to Firestore.

    Each row must already be validated and sanitized by the caller (the PUT
    /api/trips handler). Returns the list of document ids created.

    date_confirmed is stored per trip so the engine can decide whether to use
    trip_date for period-boundary comparisons (FE-3).
    """
    ids = []
    col = _user_ref(uid).collection("trips")
    for row in trip_rows:
        doc_id = row.get("trip_id") or str(uuid.uuid4())
        col.document(doc_id).set({**row, "saved_at": datetime.datetime.utcnow().isoformat()})
        ids.append(doc_id)
    return ids


def get_trips(uid: str) -> List[Dict[str, Any]]:
    """Return all stored trip documents for the user."""
    col = _user_ref(uid).collection("trips")
    return [doc.to_dict() for doc in col.stream()]


# ---------------------------------------------------------------------------
# Weeks
# ---------------------------------------------------------------------------

def save_week(uid: str, week_row: Dict[str, Any]) -> str:
    """Write one confirmed weekly summary to Firestore."""
    doc_id = week_row.get("week_id") or str(uuid.uuid4())
    _user_ref(uid).collection("weeks").document(doc_id).set(
        {**week_row, "saved_at": datetime.datetime.utcnow().isoformat()}
    )
    return doc_id


def get_weeks(uid: str) -> List[Dict[str, Any]]:
    """Return all stored weekly summaries for the user."""
    col = _user_ref(uid).collection("weeks")
    return [doc.to_dict() for doc in col.stream()]


# ---------------------------------------------------------------------------
# Answers (REQUIREMENTS.md section 4.2: text, language, numbers used -- so
# text to speech, when built, can only ever speak a stored verified answer).
# ---------------------------------------------------------------------------

def save_answer(uid: str, answer_row: Dict[str, Any]) -> str:
    """Write one verified (or refused) Q&A answer to Firestore. Returns the
    new answer_id. Never stores the raw tool JSON's underlying trip/week
    documents, only the compact numbers_used dict already returned to the
    worker."""
    answer_id = str(uuid.uuid4())
    _user_ref(uid).collection("answers").document(answer_id).set(
        {**answer_row, "saved_at": datetime.datetime.utcnow().isoformat()}
    )
    return answer_id


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------

def save_costs(uid: str, cost_row: Dict[str, Any]) -> None:
    """Write (or overwrite) the worker's cost inputs.  Single document per user."""
    _user_ref(uid).collection("costs").document("current").set(cost_row)


def get_costs(uid: str) -> Optional[Dict[str, Any]]:
    """Return the stored cost inputs, or None if not yet set."""
    snap = _user_ref(uid).collection("costs").document("current").get()
    return snap.to_dict() if snap.exists else None


# ---------------------------------------------------------------------------
# Delete all
# ---------------------------------------------------------------------------

def delete_all(uid: str) -> int:
    """Delete every document under users/{uid}/ except usage counters.

    Usage counters (users/{uid}/usage/{day}) are system-owned rate-limit state.
    Deleting them would let a user reset their daily extraction limit, so they
    are intentionally excluded here.
    """
    count = 0
    user_doc_ref = _user_ref(uid)
    for sub in ("trips", "weeks", "costs", "answers"):
        for doc in user_doc_ref.collection(sub).stream():
            doc.reference.delete()
            count += 1
    return count


# ---------------------------------------------------------------------------
# Helpers used by the engine endpoints
# ---------------------------------------------------------------------------

def _to_trip_input(row: Dict[str, Any]):
    """Convert a Firestore trip dict to engine.models.TripInput."""
    from engine.models import TripInput
    return TripInput(
        base_pay=row.get("base_pay"),
        incentive=row.get("incentive"),
        tip=row.get("tip"),
        deductions=[d["amount"] for d in row.get("deductions", []) if isinstance(d, dict)],
        total_payout=row.get("total_payout"),
        distance_km=row.get("distance_km"),
        duration_min=row.get("duration_min"),
        trip_date=row.get("trip_date"),
        date_confirmed=bool(row.get("date_confirmed", False)),
    )


def _to_week_input(row: Dict[str, Any]):
    """Convert a Firestore week dict to engine.models.WeekInput."""
    from engine.models import PayoutLine, WeekInput
    lines = [PayoutLine(label=l["label"], amount=l["amount"]) for l in row.get("lines", [])]
    return WeekInput(
        lines=lines,
        deductions=[d["amount"] for d in row.get("deductions", []) if isinstance(d, dict)],
        total_credited=row.get("total_credited"),
        km_driven=row.get("km_driven"),
        hours_online=row.get("hours_online"),
    )


def _to_cost_inputs(row: Optional[Dict[str, Any]]):
    """Convert a Firestore costs dict to engine.models.CostInputs.

    Raises ApiError if the document is missing.
    """
    from engine.models import CostInputs
    if row is None:
        raise ApiError(400, "costs_not_set", "Please enter your fuel and maintenance costs first.")
    return CostInputs(
        fuel_cost_per_km=float(row.get("fuel_cost_per_km", 0)),
        maintenance_cost_per_km=float(row.get("maintenance_cost_per_km", 0)),
        fixed_cost_per_day=row.get("fixed_cost_per_day"),
    )
