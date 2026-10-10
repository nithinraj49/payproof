import logging
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, Query, UploadFile
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.auth import require_user_id
from backend.config import get_settings
from backend.errors import ApiError, api_error_handler, http_exception_handler
from backend.extraction_cache import get_cached, hash_image, set_cached
from backend.gemini_client import get_client
from backend.sample_cache import get_cached_sample, set_cached_sample
from backend.qa import ask_question
from backend.report import render_trip_report, render_weekly_report
from backend.store import (
    _to_cost_inputs, _to_trip_input, _to_week_input,
    delete_all, get_costs, get_trips, get_weeks,
    save_answer, save_costs, save_trips, save_week,
)
from backend.usage_limits import check_and_increment
from engine.changes import detect_change
from engine.earnings import compute_trip_summary, compute_weekly_summary
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

    # Per-call token/cost logging happens inside extract_screenshot() itself
    # (extraction/extract.py's "payproof.gemini_calls" JSON line), not here --
    # that is the one line per Gemini call with no user id, per REQUIREMENTS.md
    # section 19.
    if is_sample:
        set_cached_sample(image_hash, outcome.result)
    else:
        set_cached(image_hash, outcome.result)
    return outcome.result.model_dump()


# ---------------------------------------------------------------------------
# Request bodies for the storage endpoints
# ---------------------------------------------------------------------------

class DeductionBody(BaseModel):
    label: str
    amount: float = Field(ge=0)


class TripBody(BaseModel):
    trip_id: Optional[str] = None
    trip_date: Optional[str] = None
    date_confirmed: bool = False
    base_pay: Optional[float] = Field(None, ge=0)
    incentive: Optional[float] = Field(None, ge=0)
    tip: Optional[float] = Field(None, ge=0)
    deductions: List[DeductionBody] = []
    total_payout: Optional[float] = Field(None, ge=0)
    distance_km: Optional[float] = Field(None, ge=0)
    duration_min: Optional[float] = Field(None, ge=0)


class PutTripsBody(BaseModel):
    trips: List[TripBody]


class PayoutLineBody(BaseModel):
    label: str
    amount: float = Field(ge=0)


class WeekBody(BaseModel):
    week_id: Optional[str] = None
    period_label: Optional[str] = None
    lines: List[PayoutLineBody] = []
    deductions: List[DeductionBody] = []
    total_credited: Optional[float] = Field(None, ge=0)
    km_driven: Optional[float] = Field(None, ge=0)
    hours_online: Optional[float] = Field(None, ge=0)


class CostsBody(BaseModel):
    fuel_cost_per_km: float = Field(ge=0)
    maintenance_cost_per_km: float = Field(ge=0)
    fixed_cost_per_day: Optional[float] = Field(None, ge=0)


# ---------------------------------------------------------------------------
# Storage endpoints
# ---------------------------------------------------------------------------

@app.put("/api/trips")
def put_trips(body: PutTripsBody, user_id: str = Depends(require_user_id)):
    """Save confirmed trips for this user.  Replaces any trips with the same
    trip_id; new rows get a server-generated id.
    """
    rows = [t.model_dump() for t in body.trips]
    ids = save_trips(user_id, rows)
    return {"saved": len(ids), "trip_ids": ids}


@app.put("/api/weeks")
def put_weeks(body: WeekBody, user_id: str = Depends(require_user_id)):
    """Save one confirmed weekly summary for this user."""
    doc_id = save_week(user_id, body.model_dump())
    return {"saved": 1, "week_id": doc_id}


@app.put("/api/costs")
def put_costs(body: CostsBody, user_id: str = Depends(require_user_id)):
    """Save (or overwrite) cost inputs for this user."""
    save_costs(user_id, body.model_dump())
    return {"saved": True}


@app.get("/api/summary")
def get_summary(
    mode: str = Query("trip", pattern="^(trip|weekly)$"),
    logged_in_hours: Optional[float] = Query(None, ge=0),
    user_id: str = Depends(require_user_id),
):
    """Return engine summary for the user's stored data.

    mode=trip: trip-mode summary from stored trip rows.
    mode=weekly: weekly-mode summary from stored week rows (most recent week).
    """
    costs_row = get_costs(user_id)
    cost_inputs = _to_cost_inputs(costs_row)

    if mode == "trip":
        trip_rows = get_trips(user_id)
        if not trip_rows:
            raise ApiError(400, "no_trips", "No confirmed trips found. Please upload and confirm trip screenshots first.")
        trip_inputs = [_to_trip_input(r) for r in trip_rows]
        try:
            summary = compute_trip_summary(trip_inputs, cost_inputs, logged_in_hours=logged_in_hours)
        except ValueError as exc:
            raise ApiError(400, "invalid_data", str(exc))
        return {
            "mode": "trip",
            "gross_pay": summary.gross_pay,
            "platform_deductions": summary.platform_deductions,
            "net_payout": summary.net_payout,
            "worker_costs": summary.worker_costs,
            "net_earnings": summary.net_earnings,
            "engaged_hours": summary.engaged_hours,
            "net_per_engaged_hour": summary.net_per_engaged_hour,
            "net_per_logged_in_hour": summary.net_per_logged_in_hour,
            "net_payout_per_km": summary.net_payout_per_km,
            "deduction_share": summary.deduction_share,
            "total_distance_km": summary.total_distance_km,
            "trip_count": summary.trip_count,
            "data_quality": summary.data_quality,
        }

    # weekly mode: use the most recently saved week
    week_rows = get_weeks(user_id)
    if not week_rows:
        raise ApiError(400, "no_weeks", "No confirmed weekly summaries found. Please upload and confirm a weekly payout screenshot first.")
    latest = sorted(week_rows, key=lambda r: r.get("saved_at", ""), reverse=True)[0]
    week_input = _to_week_input(latest)
    try:
        summary = compute_weekly_summary(week_input, cost_inputs)
    except ValueError as exc:
        raise ApiError(400, "invalid_data", str(exc))
    return {
        "mode": "weekly",
        "gross_weekly": summary.gross_weekly,
        "deductions_weekly": summary.deductions_weekly,
        "net_payout_weekly": summary.net_payout_weekly,
        "reconciliation_gap": summary.reconciliation_gap,
        "worker_costs_weekly": summary.worker_costs_weekly,
        "net_earnings_weekly": summary.net_earnings_weekly,
        "net_per_online_hour": summary.net_per_online_hour,
        "net_payout_per_km": summary.net_payout_per_km,
        "deduction_share": summary.deduction_share,
        "per_hour_on_trips_unavailable": summary.per_hour_on_trips_unavailable,
        "data_quality": summary.data_quality,
    }


@app.get("/api/changes")
def get_changes(
    split_date: Optional[str] = Query(None, description="ISO date splitting baseline/recent periods"),
    user_id: str = Depends(require_user_id),
):
    """Return trip-mode pay-change signal.

    Splits stored trips at split_date (baseline = before, recent = on or after).
    If no split_date given, splits at the ISO week boundary of the median date.
    Returns insufficient_data if either period has fewer than 15 confirmed trips.

    Disabled by default (ENABLE_CHANGE_SIGNAL=false): offline evaluation on
    simulated data (eval/compare_estimators.py) found no estimator gives
    usable recall with zero false alarms, so the feature returns "unavailable"
    and does no computation unless explicitly re-enabled. See eval/RESULTS.md.
    """
    if not get_settings().enable_change_signal:
        return {
            "status": "unavailable",
            "reason": "Pay-change detection was tested on simulated data and found unreliable, so it is disabled.",
        }

    trip_rows = get_trips(user_id)
    if not trip_rows:
        raise ApiError(400, "no_trips", "No confirmed trips found.")

    trip_inputs = [_to_trip_input(r) for r in trip_rows]

    if split_date:
        baseline = [t for t in trip_inputs if t.trip_date and t.trip_date < split_date]
        recent = [t for t in trip_inputs if t.trip_date and t.trip_date >= split_date]
    else:
        # Default: split at median date of confirmed trips
        dated = sorted(
            [t for t in trip_inputs if t.trip_date and t.date_confirmed],
            key=lambda t: t.trip_date,
        )
        if len(dated) < 2:
            return {
                "status": "insufficient_data",
                "reason": "Not enough trips with confirmed dates to split into periods.",
                "baseline_count": 0, "recent_count": 0, "excluded_unconfirmed": 0,
            }
        mid = dated[len(dated) // 2].trip_date
        baseline = [t for t in trip_inputs if t.trip_date and t.trip_date < mid]
        recent = [t for t in trip_inputs if t.trip_date and t.trip_date >= mid]

    result = detect_change(baseline, recent)
    return {
        "status": result.status,
        "metric": result.metric,
        "baseline_mean": result.baseline_mean,
        "recent_mean": result.recent_mean,
        "relative_change": result.relative_change,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "baseline_count": result.baseline_count,
        "recent_count": result.recent_count,
        "excluded_unconfirmed": result.excluded_unconfirmed,
        "reason": result.reason,
    }


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    language: str = "en"  # English only for now (CLAUDE.md); kept so a language can be added later.


@app.post("/api/ask")
def ask(body: AskBody, user_id: str = Depends(require_user_id)):
    """Grounded Q&A (REQUIREMENTS.md section 7). Every number in the answer
    is checked against engine output before it is ever shown; a question that
    can't be answered this way gets a plain refusal instead, never a guess.
    """
    settings = get_settings()
    if body.language != "en":
        raise ApiError(400, "unsupported_language", "Only English is supported right now.")

    check_and_increment(user_id, "questions", settings.limit_questions_per_user_per_day, settings.limit_global_gemini_calls_per_day)

    client = get_client(settings)
    try:
        result = ask_question(client, settings, settings.explain_model, user_id, body.question, body.language)
    except RateLimitError:
        raise ApiError(503, "service_busy", "PayProof is busy right now. Please try again in a minute.")

    # Per-call token/cost logging happens inside ask_question() itself
    # (backend/qa.py's "payproof.gemini_calls" JSON line), not here.
    answer_id = save_answer(user_id, {
        "question": body.question,
        "language": body.language,
        "text": result.text,
        "verified": result.verified,
        "numbers_used": result.numbers_used,
    })
    return {
        "answer_id": answer_id,
        "text": result.text,
        "verified": result.verified,
        "numbers_used": result.numbers_used,
    }


@app.get("/api/report")
def get_report(
    mode: str = Query("trip", pattern="^(trip|weekly)$"),
    logged_in_hours: Optional[float] = Query(None, ge=0),
    user_id: str = Depends(require_user_id),
):
    """Evidence pack HTML (REQUIREMENTS.md section 8): a plain, self-contained
    page with a summary table, the method in words, data-quality notes, and
    the privacy/limits statement. No names or phone numbers (none are ever
    extracted or stored). All user-supplied label text is HTML-escaped."""
    costs_row = get_costs(user_id)
    cost_inputs = _to_cost_inputs(costs_row)

    if mode == "trip":
        trip_rows = get_trips(user_id)
        if not trip_rows:
            raise ApiError(400, "no_trips", "No confirmed trips found. Please upload and confirm trip screenshots first.")
        trip_inputs = [_to_trip_input(r) for r in trip_rows]
        try:
            summary = compute_trip_summary(trip_inputs, cost_inputs, logged_in_hours=logged_in_hours)
        except ValueError as exc:
            raise ApiError(400, "invalid_data", str(exc))
        html_doc = render_trip_report(summary, trip_rows)
    else:
        week_rows = get_weeks(user_id)
        if not week_rows:
            raise ApiError(400, "no_weeks", "No confirmed weekly summaries found. Please upload and confirm a weekly payout screenshot first.")
        latest = sorted(week_rows, key=lambda r: r.get("saved_at", ""), reverse=True)[0]
        week_input = _to_week_input(latest)
        try:
            summary = compute_weekly_summary(week_input, cost_inputs)
        except ValueError as exc:
            raise ApiError(400, "invalid_data", str(exc))
        html_doc = render_weekly_report(summary, latest)

    return HTMLResponse(content=html_doc)


@app.delete("/api/data")
def delete_data(user_id: str = Depends(require_user_id)):
    """Delete all stored data for this user (REQUIREMENTS.md sections 2 and 11)."""
    count = delete_all(user_id)
    logger.info("delete uid=%s documents_deleted=%d", user_id, count)
    return {"deleted": True, "documents_removed": count}
