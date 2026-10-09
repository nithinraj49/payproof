"""Tests for the deterministic post-extraction safeguards (extraction/extract.py).
Pure code, no Gemini calls, no network."""
from extraction.extract import apply_deterministic_safeguards, normalize_low_confidence_labels
from extraction.schema import Deduction, ExtractionResult, Trip


def make_result(trip: Trip, needs_review: bool = False) -> ExtractionResult:
    return ExtractionResult(screen_type="trip_detail", trips=[trip], payout_summary=None, needs_review=needs_review)


def test_clean_trip_is_unchanged():
    trip = Trip(base_pay=100.0, total_payout=100.0, distance_km=5.0, duration_min=20.0)
    result = apply_deterministic_safeguards(make_result(trip))
    t = result.trips[0]
    assert t.base_pay == 100.0
    assert t.total_payout == 100.0
    assert t.distance_km == 5.0
    assert t.duration_min == 20.0
    assert result.needs_review is False


def test_a_low_confidence_field_becomes_null_and_flags_review():
    trip = Trip(base_pay=50.0, total_payout=50.0, low_confidence_fields=["base_pay"])
    result = apply_deterministic_safeguards(make_result(trip))
    t = result.trips[0]
    assert t.base_pay is None
    assert result.needs_review is True
    assert "base_pay" in t.low_confidence_fields


def test_b_reconciliation_mismatch_nulls_all_money_fields():
    # base(50) + incentive(10) + tip(5) - deductions(0) = 65, but total_payout says 200: mismatch
    trip = Trip(base_pay=50.0, incentive=10.0, tip=5.0, total_payout=200.0)
    result = apply_deterministic_safeguards(make_result(trip))
    t = result.trips[0]
    assert t.base_pay is None
    assert t.incentive is None
    assert t.tip is None
    assert t.total_payout is None
    assert result.needs_review is True
    assert set(t.low_confidence_fields) == {"base_pay", "incentive", "tip", "total_payout"}


def test_b_reconciliation_within_tolerance_is_not_flagged():
    # 50 + 0 + 0 - 0 = 50, total_payout 50.3: within the 0.5 tolerance
    trip = Trip(base_pay=50.0, total_payout=50.3)
    result = apply_deterministic_safeguards(make_result(trip))
    t = result.trips[0]
    assert t.base_pay == 50.0
    assert t.total_payout == 50.3
    assert result.needs_review is False


def test_b_reconciliation_accounts_for_deductions():
    trip = Trip(base_pay=100.0, deductions=[Deduction(label="fee", amount=10.0)], total_payout=90.0)
    result = apply_deterministic_safeguards(make_result(trip))
    t = result.trips[0]
    assert t.base_pay == 100.0  # 100 - 10 = 90, matches total_payout, no mismatch
    assert t.total_payout == 90.0
    assert result.needs_review is False


def test_c_implausible_future_date_becomes_null():
    trip = Trip(trip_date="2099-01-01", base_pay=10.0, total_payout=10.0)
    result = apply_deterministic_safeguards(make_result(trip))
    assert result.trips[0].trip_date is None
    assert result.needs_review is True


def test_c_implausible_old_date_becomes_null():
    trip = Trip(trip_date="1999-05-05", base_pay=10.0, total_payout=10.0)
    result = apply_deterministic_safeguards(make_result(trip))
    assert result.trips[0].trip_date is None


def test_c_plausible_date_is_kept():
    trip = Trip(trip_date="2026-01-15", base_pay=10.0, total_payout=10.0)
    result = apply_deterministic_safeguards(make_result(trip))
    assert result.trips[0].trip_date == "2026-01-15"
    assert result.needs_review is False


def test_d_zero_distance_and_duration_become_null():
    # Negative values can't reach this point at all: extraction/schema.py already
    # enforces ge=0 on both fields, so the model's structured output is rejected
    # (a schema-validation retry) before a negative number ever becomes a Trip.
    # Zero is schema-valid but not a plausible real trip, so it's this
    # safeguard's job.
    trip = Trip(base_pay=10.0, total_payout=10.0, distance_km=0.0, duration_min=0.0)
    result = apply_deterministic_safeguards(make_result(trip))
    t = result.trips[0]
    assert t.distance_km is None
    assert t.duration_min is None
    assert result.needs_review is True


def test_d_positive_distance_and_duration_are_kept():
    trip = Trip(base_pay=10.0, total_payout=10.0, distance_km=3.5, duration_min=12.0)
    result = apply_deterministic_safeguards(make_result(trip))
    t = result.trips[0]
    assert t.distance_km == 3.5
    assert t.duration_min == 12.0


def test_already_needs_review_stays_true_even_without_new_changes():
    trip = Trip(base_pay=10.0, total_payout=10.0)
    result = apply_deterministic_safeguards(make_result(trip, needs_review=True))
    assert result.needs_review is True


def test_result_with_no_trips_is_a_no_op():
    result = ExtractionResult(screen_type="order_offer", trips=[], payout_summary=None, needs_review=False)
    out = apply_deterministic_safeguards(result)
    assert out.screen_type == "order_offer"
    assert out.needs_review is False


# --- normalize_low_confidence_labels: the H1_006 regression ---

def test_normalizer_h1_006_exact_labels():
    # The exact raw output recorded for H1_006 during the Vertex hard-tier eval:
    # human labels instead of schema field names, one of which ("Platform fee")
    # doesn't correspond to any Trip field at all.
    data = {
        "screen_type": "trip_detail",
        "needs_review": True,
        "trips": [{
            "trip_date": None, "order_id": "888-2763", "order_type": "Passenger ride",
            "base_pay": 113.68, "incentive": None, "tip": None,
            "deductions": [{"label": "Platform fee", "amount": 15.16}],
            "total_payout": 98.52, "distance_km": None, "duration_min": None,
            "low_confidence_fields": ["Date", "Base pay", "Platform fee", "Total payout"],
        }],
        "payout_summary": None,
    }
    normalized = normalize_low_confidence_labels(data)
    trip = normalized["trips"][0]
    # "Date" -> trip_date, "Base pay" -> base_pay, "Total payout" -> total_payout all recognized;
    # "Platform fee" is NOT a Trip field, so the conservative fallback adds every money field.
    assert set(trip["low_confidence_fields"]) == {"trip_date", "base_pay", "total_payout", "incentive", "tip"}
    assert normalized["needs_review"] is True

    # Running the full pipeline (normalize then safeguards) should null every money field.
    result = apply_deterministic_safeguards(ExtractionResult.model_validate(normalized))
    t = result.trips[0]
    assert t.base_pay is None
    assert t.incentive is None
    assert t.tip is None
    assert t.total_payout is None
    assert result.needs_review is True


def test_normalizer_recognizes_canonical_names_unchanged():
    data = {
        "screen_type": "trip_detail", "needs_review": False,
        "trips": [{"base_pay": 10.0, "total_payout": 10.0, "low_confidence_fields": ["base_pay"]}],
        "payout_summary": None,
    }
    normalized = normalize_low_confidence_labels(data)
    assert normalized["trips"][0]["low_confidence_fields"] == ["base_pay"]
    assert normalized["needs_review"] is False


def test_normalizer_payout_summary_unrecognized_label_is_conservative():
    data = {
        "screen_type": "payout_summary", "needs_review": False, "trips": [],
        "payout_summary": {
            "lines": [], "deductions": [], "total_credited": 100.0,
            "low_confidence_fields": ["Some Weird Label"],
        },
    }
    normalized = normalize_low_confidence_labels(data)
    assert normalized["payout_summary"]["low_confidence_fields"] == ["total_credited"]
    assert normalized["needs_review"] is True


def test_normalizer_no_trips_or_summary_is_a_no_op():
    data = {"screen_type": "order_offer", "needs_review": False, "trips": [], "payout_summary": None}
    normalized = normalize_low_confidence_labels(data)
    assert normalized["needs_review"] is False
