"""Ad-hoc analysis of eval/results/<model>/*.json against ground truth: exact
method used for "field accuracy", per-field breakdown, breakdown by noise
type, and near-misses (wrong but close). Reads only already-saved data —
makes no Gemini calls.

Usage: python -m eval.analyze_model_selection
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "eval" / "generated" / "manifest.json").read_text())
MANIFEST_BY_NAME = {e["name"]: e for e in MANIFEST}

TOLERANCE = 0.5  # same tolerance used during model selection
NEAR_MISS_MAX = 2.0  # wrong but within this absolute difference is reported separately

TRIP_FIELDS = ["base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min"]
PAYOUT_FIELDS = ["total_credited"]


def load_ground_truth(name):
    return json.loads((ROOT / "eval" / "generated" / "ground_truth" / f"{name}.json").read_text())


def analyze(model: str):
    model_dir = ROOT / "eval" / "results" / model
    field_results = []  # (name, field, pred, truth, status) status in {correct, wrong, near_miss, missing}
    noise_tally = {}  # noise -> {correct, total}

    for path in sorted(model_dir.glob("*.json")):
        record = json.loads(path.read_text())
        name = record["name"]
        layout = record["layout"]
        gt = load_ground_truth(name)
        noise = MANIFEST_BY_NAME[name]["noise"]
        noise_tally.setdefault(noise, {"correct": 0, "total": 0})

        fields = []
        if layout == "L1":
            pred_trip = record["predicted"]["trips"][0] if record["predicted"]["trips"] else {}
            gt_trip = gt["trips"][0]
            fields = [(f, pred_trip.get(f), gt_trip.get(f)) for f in TRIP_FIELDS]
        elif layout == "L3":
            pred_summary = record["predicted"]["payout_summary"] or {}
            gt_summary = gt["payout_summary"]
            fields = [(f, pred_summary.get(f), gt_summary.get(f)) for f in PAYOUT_FIELDS]
        # N1 has no numeric fields to score here; its correctness is rejection, not field accuracy.

        for field, pred, truth in fields:
            if truth is None:
                continue  # not applicable to this image, excluded from the denominator
            noise_tally[noise]["total"] += 1
            if pred is None:
                status = "missing"
            else:
                diff = abs(pred - truth)
                if diff <= TOLERANCE:
                    status = "correct"
                    noise_tally[noise]["correct"] += 1
                elif diff <= NEAR_MISS_MAX:
                    status = "near_miss"
                else:
                    status = "wrong"
            field_results.append({"name": name, "layout": layout, "noise": noise, "field": field,
                                   "pred": pred, "truth": truth, "status": status})

    return field_results, noise_tally


def print_report(model: str):
    print(f"\n{'='*60}\n{model}\n{'='*60}")
    field_results, noise_tally = analyze(model)

    by_field = {}
    for r in field_results:
        by_field.setdefault(r["field"], {"correct": 0, "total": 0})
        by_field[r["field"]]["total"] += 1
        if r["status"] == "correct":
            by_field[r["field"]]["correct"] += 1

    print("Per-field accuracy:")
    for field, stats in by_field.items():
        pct = round(100 * stats["correct"] / stats["total"], 1) if stats["total"] else None
        print(f"  {field}: {stats['correct']}/{stats['total']} ({pct}%)")

    print("\nBy noise type:")
    for noise, stats in sorted(noise_tally.items()):
        pct = round(100 * stats["correct"] / stats["total"], 1) if stats["total"] else None
        print(f"  {noise}: {stats['correct']}/{stats['total']} ({pct}%)")

    non_correct = [r for r in field_results if r["status"] != "correct"]
    print(f"\nNon-correct fields ({len(non_correct)}):")
    for r in non_correct:
        print(f"  {r['name']} [{r['noise']}] {r['field']}: pred={r['pred']} truth={r['truth']} -> {r['status']}")
    if not non_correct:
        print("  (none)")


if __name__ == "__main__":
    for model in ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]:
        print_report(model)
