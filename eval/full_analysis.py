"""Offline re-analysis of all saved eval/results/vertex_extraction_eval/*.json
records (zero Gemini calls). This is analysis tooling, not production code --
it never touches extraction/ or backend/, makes no Gemini calls, and nothing
here is deployed.

  - strict vs lenient tolerance, reported side by side
  - "failed_call" (transport/server error -> the fallback response) as an
    outcome distinct from "abstained" (the model actually responded, flagged
    a field, and returned null)
  - "gate_blocked" (the image-quality gate rejected it before any Gemini
    call) as an outcome distinct from both
  - scoring for deductions (amount + label), weekly lines (amount + label),
    weekly deductions, trip_date, and the weekly period fields
  - if a field a ground-truth record should have is genuinely absent from
    the dict (not just null), this is reported explicitly, never guessed
  - N1 (order-offer rejection) is a single image-level judgment, not a field,
    so it is tallied and reported SEPARATELY from the field-level table --
    blending it into the same denominator was the bug that made the standard
    set's headline number (177, correct 176 + 1 silent gap) not match its
    own per-field rows (172; 171 correct + 1 silent gap). Fixed here.
  - for every wrong (non-null, incorrect) field, whether that SPECIFIC field
    name was listed in low_confidence_fields, vs only flagged through the
    image-level needs_review -- so "wrong, flagged" can be split into
    "field individually highlighted" vs "only the image-level flag caught it"

Usage: python -m eval.full_analysis
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "eval" / "results" / "vertex_extraction_eval"
MANIFEST = json.loads((ROOT / "eval" / "generated" / "manifest.json").read_text())
MANIFEST_BY_NAME = {e["name"]: e for e in MANIFEST}

LENIENT_TOLERANCE = 0.5
STRICT_TOLERANCE = {
    "base_pay": 0.005, "incentive": 0.005, "tip": 0.005, "total_payout": 0.005,
    "total_credited": 0.005, "amount": 0.005,  # deduction/line amounts
    "distance_km": 0.1,
    "duration_min": 0.0,
}

FALLBACK_NOTES = {
    "Could not read this screenshot right now. Please try again.",
    "Could not read this screenshot reliably. Please try a clearer photo.",
}

OUTCOME_KEYS = ["correct", "abstained", "failed_call", "gate_blocked", "wrong_flagged", "confidently_wrong", "missing_not_flagged"]

# Trip/payout fields whose name can appear in low_confidence_fields (matches
# extraction/schema.py's TripField/PayoutField literals). Deduction and line
# entries have no single field name to check individually in the schema, so
# they're reported as "no per-field flag exists for this kind of value".
TRIP_FLAGGABLE_FIELDS = {"trip_date", "order_id", "order_type", "base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min"}
PAYOUT_FLAGGABLE_FIELDS = {"period_label", "period_start", "period_end", "total_credited", "credited_on"}


def new_tally():
    return {k: 0 for k in OUTCOME_KEYS}


def merge(a, b):
    for k in b:
        a[k] = a.get(k, 0) + b[k]
    return a


def classify(pred, truth, needs_review, failed_call, gate_blocked, tolerance):
    if truth is None:
        return None
    if gate_blocked:
        return "gate_blocked"
    if failed_call:
        return "failed_call"
    if pred is None:
        return "abstained" if needs_review else "missing_not_flagged"
    if isinstance(truth, str) or isinstance(pred, str):
        match = pred == truth
    else:
        match = abs(pred - truth) <= tolerance
    if match:
        return "correct"
    return "wrong_flagged" if needs_review else "confidently_wrong"


def get_missing(d: dict, field: str, name: str, context: str, missing_log: list):
    if field not in d:
        missing_log.append(f"{name} [{context}]: ground truth is missing key {field!r} entirely (not just null)")
        return None
    return d[field]


def score_trip(pred: dict, gt: dict, name: str, strict: bool, missing_log: list) -> dict:
    tally = new_tally()
    needs_review = pred.get("needs_review", False)
    failed_call = pred.get("notes") in FALLBACK_NOTES
    gate_blocked = pred.get("gate_blocked_marker", False)

    pred_trip = pred["trips"][0] if pred.get("trips") else {}
    if not gt.get("trips"):
        return tally  # nothing to score (shouldn't happen for L1/H1/M1 ground truth)
    gt_trip = gt["trips"][0]

    numeric_fields = ["base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min"]
    for f in numeric_fields:
        t = get_missing(gt_trip, f, name, "trip", missing_log)
        tol = STRICT_TOLERANCE[f] if strict else LENIENT_TOLERANCE
        outcome = classify(pred_trip.get(f), t, needs_review, failed_call, gate_blocked, tol)
        if outcome:
            tally[outcome] += 1

    t_date = get_missing(gt_trip, "trip_date", name, "trip", missing_log)
    outcome = classify(pred_trip.get("trip_date"), t_date, needs_review, failed_call, gate_blocked, 0)
    if outcome:
        tally[outcome] += 1

    # deductions: our simulator never produces more than one per trip, so index-position
    # comparison is valid; if that ever changes, this would need label-based matching.
    gt_deductions = get_missing(gt_trip, "deductions", name, "trip", missing_log) or []
    pred_deductions = pred_trip.get("deductions") or []
    for i, gt_d in enumerate(gt_deductions):
        pred_d = pred_deductions[i] if i < len(pred_deductions) else None
        tol = STRICT_TOLERANCE["amount"] if strict else LENIENT_TOLERANCE
        amt_outcome = classify(pred_d["amount"] if pred_d else None, gt_d["amount"], needs_review, failed_call, gate_blocked, tol)
        lbl_outcome = classify(pred_d["label"] if pred_d else None, gt_d["label"], needs_review, failed_call, gate_blocked, 0)
        if amt_outcome:
            tally[amt_outcome] += 1
        if lbl_outcome:
            tally[lbl_outcome] += 1

    return tally


def score_payout_summary(pred: dict, gt: dict, name: str, strict: bool, missing_log: list) -> dict:
    tally = new_tally()
    needs_review = pred.get("needs_review", False)
    failed_call = pred.get("notes") in FALLBACK_NOTES
    gate_blocked = pred.get("gate_blocked_marker", False)

    pred_summary = pred.get("payout_summary") or {}
    gt_summary = gt.get("payout_summary")
    if not gt_summary:
        return tally

    tol = STRICT_TOLERANCE["total_credited"] if strict else LENIENT_TOLERANCE
    t = get_missing(gt_summary, "total_credited", name, "payout_summary", missing_log)
    outcome = classify(pred_summary.get("total_credited"), t, needs_review, failed_call, gate_blocked, tol)
    if outcome:
        tally[outcome] += 1

    # period_start and period_end are deliberately NOT scored: eval/generate_data.py's
    # L3 layout never draws them on screen (only period_label and credited_on are
    # visible) -- scoring them would penalize the model for correctly not guessing
    # data that was never shown.
    for f in ["period_label", "credited_on"]:
        t = get_missing(gt_summary, f, name, "payout_summary", missing_log)
        outcome = classify(pred_summary.get(f), t, needs_review, failed_call, gate_blocked, 0)
        if outcome:
            tally[outcome] += 1

    gt_lines = get_missing(gt_summary, "lines", name, "payout_summary", missing_log) or []
    pred_lines = pred_summary.get("lines") or []
    for i, gt_l in enumerate(gt_lines):
        pred_l = pred_lines[i] if i < len(pred_lines) else None
        line_tol = STRICT_TOLERANCE["amount"] if strict else LENIENT_TOLERANCE
        amt_outcome = classify(pred_l["amount"] if pred_l else None, gt_l["amount"], needs_review, failed_call, gate_blocked, line_tol)
        lbl_outcome = classify(pred_l["label"] if pred_l else None, gt_l["label"], needs_review, failed_call, gate_blocked, 0)
        if amt_outcome:
            tally[amt_outcome] += 1
        if lbl_outcome:
            tally[lbl_outcome] += 1

    gt_deductions = get_missing(gt_summary, "deductions", name, "payout_summary", missing_log) or []
    pred_deductions = pred_summary.get("deductions") or []
    for i, gt_d in enumerate(gt_deductions):
        pred_d = pred_deductions[i] if i < len(pred_deductions) else None
        ded_tol = STRICT_TOLERANCE["amount"] if strict else LENIENT_TOLERANCE
        amt_outcome = classify(pred_d["amount"] if pred_d else None, gt_d["amount"], needs_review, failed_call, gate_blocked, ded_tol)
        lbl_outcome = classify(pred_d["label"] if pred_d else None, gt_d["label"], needs_review, failed_call, gate_blocked, 0)
        if amt_outcome:
            tally[amt_outcome] += 1
        if lbl_outcome:
            tally[lbl_outcome] += 1

    return tally


def score_n1(pred: dict) -> dict:
    """N1 is a single image-level judgment (rejected or not), not a field --
    tallied and reported separately from the field-level table, never blended
    into the same denominator."""
    tally = new_tally()
    gate_blocked = pred.get("gate_blocked_marker", False)
    if gate_blocked:
        tally["gate_blocked"] += 1
        return tally
    rejected = pred.get("screen_type") == "order_offer" and not pred.get("trips") and pred.get("payout_summary") is None
    tally["correct" if rejected else "confidently_wrong"] += 1
    return tally


def analyze_tier(names: list, strict: bool, missing_log: list) -> dict:
    """Returns {"fields": tally, "n1": tally}. The two are never summed into
    one number: fields has a per-field breakdown, n1 does not (it can't --
    it's one judgment per image, not a set of fields)."""
    field_tally = new_tally()
    n1_tally = new_tally()
    for name in names:
        p = RESULTS_DIR / f"{name}.json"
        if not p.exists():
            continue
        rec = json.loads(p.read_text())
        entry = MANIFEST_BY_NAME[name]
        gt = json.loads((ROOT / entry["ground_truth"]).read_text())
        pred = dict(rec["predicted"])
        pred["gate_blocked_marker"] = rec.get("gate_blocked", False)

        layout = entry["layout"]
        if layout in ("L1", "H1", "M1"):
            field_tally = merge(field_tally, score_trip(pred, gt, name, strict, missing_log))
        elif layout == "L3":
            field_tally = merge(field_tally, score_payout_summary(pred, gt, name, strict, missing_log))
        elif layout == "N1":
            n1_tally = merge(n1_tally, score_n1(pred))
    return {"fields": field_tally, "n1": n1_tally}


def wrong_flag_breakdown(names: list) -> dict:
    """For every lenient-tolerance wrong-but-flagged field (image-level
    needs_review=true, value non-null and wrong), checks whether that SPECIFIC
    field name was also individually listed in low_confidence_fields, versus
    only caught by the image-level flag. Deduction/line amounts and labels
    have no individual field name in the schema to check, so they're counted
    separately as "no per-field flag exists for this kind of value"."""
    individually_flagged = 0
    image_level_only = 0
    no_per_field_flag_exists = 0
    rows = []

    for name in names:
        p = RESULTS_DIR / f"{name}.json"
        if not p.exists():
            continue
        rec = json.loads(p.read_text())
        entry = MANIFEST_BY_NAME[name]
        gt = json.loads((ROOT / entry["ground_truth"]).read_text())
        pred = dict(rec["predicted"])
        needs_review = pred.get("needs_review", False)
        failed_call = pred.get("notes") in FALLBACK_NOTES
        gate_blocked = rec.get("gate_blocked", False)
        layout = entry["layout"]

        if layout in ("L1", "H1", "M1") and gt.get("trips"):
            pred_trip = pred["trips"][0] if pred.get("trips") else {}
            gt_trip = gt["trips"][0]
            lcf = set(pred_trip.get("low_confidence_fields") or [])
            for f in ["base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min", "trip_date"]:
                t = gt_trip.get(f)
                outcome = classify(pred_trip.get(f), t, needs_review, failed_call, gate_blocked, LENIENT_TOLERANCE)
                if outcome == "wrong_flagged":
                    if f in lcf:
                        individually_flagged += 1
                        rows.append((name, f, "individually_flagged"))
                    else:
                        image_level_only += 1
                        rows.append((name, f, "image_level_only"))
            for i, gt_d in enumerate(gt_trip.get("deductions") or []):
                pred_deds = pred_trip.get("deductions") or []
                pred_d = pred_deds[i] if i < len(pred_deds) else None
                amt_o = classify(pred_d["amount"] if pred_d else None, gt_d["amount"], needs_review, failed_call, gate_blocked, LENIENT_TOLERANCE)
                lbl_o = classify(pred_d["label"] if pred_d else None, gt_d["label"], needs_review, failed_call, gate_blocked, 0)
                if amt_o == "wrong_flagged":
                    no_per_field_flag_exists += 1
                    rows.append((name, "deduction.amount", "no_per_field_flag_exists"))
                if lbl_o == "wrong_flagged":
                    no_per_field_flag_exists += 1
                    rows.append((name, "deduction.label", "no_per_field_flag_exists"))
        elif layout == "L3" and gt.get("payout_summary"):
            pred_summary = pred.get("payout_summary") or {}
            gt_summary = gt["payout_summary"]
            lcf = set(pred_summary.get("low_confidence_fields") or [])
            for f in ["total_credited", "period_label", "credited_on"]:
                t = gt_summary.get(f)
                outcome = classify(pred_summary.get(f), t, needs_review, failed_call, gate_blocked, LENIENT_TOLERANCE)
                if outcome == "wrong_flagged":
                    if f in lcf:
                        individually_flagged += 1
                        rows.append((name, f, "individually_flagged"))
                    else:
                        image_level_only += 1
                        rows.append((name, f, "image_level_only"))

    return {
        "individually_flagged": individually_flagged,
        "image_level_only": image_level_only,
        "no_per_field_flag_exists": no_per_field_flag_exists,
        "total_wrong_flagged": individually_flagged + image_level_only + no_per_field_flag_exists,
        "rows": rows,
    }


def detail_rows(names: list, strict: bool) -> list:
    """Like analyze_tier's field tally, but returns (name, field, pred, truth,
    outcome) for every non-correct FIELD row (N1 excluded -- it has no field)."""
    rows = []
    for name in names:
        p = RESULTS_DIR / f"{name}.json"
        if not p.exists():
            continue
        rec = json.loads(p.read_text())
        entry = MANIFEST_BY_NAME[name]
        gt = json.loads((ROOT / entry["ground_truth"]).read_text())
        pred = dict(rec["predicted"])
        pred["gate_blocked_marker"] = rec.get("gate_blocked", False)
        needs_review = pred.get("needs_review", False)
        failed_call = pred.get("notes") in FALLBACK_NOTES
        gate_blocked = pred.get("gate_blocked_marker", False)
        layout = entry["layout"]

        if layout in ("L1", "H1", "M1") and gt.get("trips"):
            pred_trip = pred["trips"][0] if pred.get("trips") else {}
            gt_trip = gt["trips"][0]
            for f in ["base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min", "trip_date"]:
                t = gt_trip.get(f)
                tol = STRICT_TOLERANCE.get(f, 0) if strict else LENIENT_TOLERANCE
                outcome = classify(pred_trip.get(f), t, needs_review, failed_call, gate_blocked, tol)
                if outcome and outcome != "correct":
                    rows.append((name, f, pred_trip.get(f), t, outcome))
            for i, gt_d in enumerate(gt_trip.get("deductions") or []):
                pred_deds = pred_trip.get("deductions") or []
                pred_d = pred_deds[i] if i < len(pred_deds) else None
                tol = STRICT_TOLERANCE["amount"] if strict else LENIENT_TOLERANCE
                amt_o = classify(pred_d["amount"] if pred_d else None, gt_d["amount"], needs_review, failed_call, gate_blocked, tol)
                lbl_o = classify(pred_d["label"] if pred_d else None, gt_d["label"], needs_review, failed_call, gate_blocked, 0)
                if amt_o and amt_o != "correct":
                    rows.append((name, "deduction.amount", pred_d["amount"] if pred_d else None, gt_d["amount"], amt_o))
                if lbl_o and lbl_o != "correct":
                    rows.append((name, "deduction.label", pred_d["label"] if pred_d else None, gt_d["label"], lbl_o))
        elif layout == "L3" and gt.get("payout_summary"):
            pred_summary = pred.get("payout_summary") or {}
            gt_summary = gt["payout_summary"]
            for f in ["total_credited", "period_label", "credited_on"]:
                t = gt_summary.get(f)
                tol = STRICT_TOLERANCE.get(f, 0) if strict else LENIENT_TOLERANCE
                outcome = classify(pred_summary.get(f), t, needs_review, failed_call, gate_blocked, tol)
                if outcome and outcome != "correct":
                    rows.append((name, f, pred_summary.get(f), t, outcome))
    return rows


def verify_reconciliation(tally: dict) -> int:
    return sum(tally.values())


def main():
    standard_names = [f"L1_{i:03d}" for i in range(1, 16)] + [f"L3_{i:03d}" for i in range(1, 11)] + [f"N1_{i:03d}" for i in range(1, 6)]
    moderate_names = [f"M1_{i:03d}" for i in range(1, 11)]
    hard_names = [f"H1_{i:03d}" for i in range(1, 11)]

    missing_log = []
    for label, names in [("STANDARD", standard_names), ("MODERATE", moderate_names), ("HARD", hard_names)]:
        print(f"=== {label} ===")
        lenient = analyze_tier(names, strict=False, missing_log=missing_log)
        strict = analyze_tier(names, strict=True, missing_log=missing_log)
        print("Lenient fields:", lenient["fields"], "  SUM =", verify_reconciliation(lenient["fields"]))
        print("Strict  fields:", strict["fields"], "  SUM =", verify_reconciliation(strict["fields"]))
        if any(lenient["n1"].values()):
            print("N1 (separate, not a field):", lenient["n1"], "  SUM =", verify_reconciliation(lenient["n1"]))
        print("Non-correct field detail (lenient):")
        for row in detail_rows(names, strict=False):
            print("  ", row)
        print("Wrong-flagged field-level breakdown:")
        wfb = wrong_flag_breakdown(names)
        print(f"   individually_flagged={wfb['individually_flagged']} image_level_only={wfb['image_level_only']} "
              f"no_per_field_flag_exists={wfb['no_per_field_flag_exists']} total={wfb['total_wrong_flagged']}")
        print()

    if missing_log:
        print("=== Fields genuinely missing from ground truth (not just null) ===")
        for line in missing_log:
            print(" ", line)
    else:
        print("No ground-truth fields were missing entirely -- every comparison had a real (possibly null) value to check against.")


if __name__ == "__main__":
    main()
