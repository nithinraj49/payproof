"""Phase 2 step B model selection: run the same 20 simulated images through
gemini-3.1-flash-lite, gemini-3.5-flash-lite and gemini-3.8-flash on the AI
Studio free tier (GEMINI_BACKEND=aistudio), and report field accuracy, the
order-offer rejection rate, average token counts, and estimated cost per call
for each model (owner's master prompt, "MODEL SELECTION (Phase 2, step B)").

This script ALWAYS prints the number of calls and the estimated cost and
waits for the owner's "go" before calling Gemini (REQUIREMENTS.md section 19
rule 9). It never calls Gemini in --dry-run mode.

Usage (PowerShell):
    python -m eval.model_selection --dry-run   # prints the cost estimate only
    python -m eval.model_selection --go        # owner has said "go": makes the calls
"""
import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from extraction.extract import extract_screenshot
from extraction.image_prep import prepare_image
from extraction.schema import ExtractionResult
from backend.config import get_settings
from backend.gemini_client import get_client

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "eval" / "generated" / "manifest.json"
RESULTS_PATH = ROOT / "eval" / "model_selection_results.json"

MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash"]

# Paid-tier prices per 1M tokens, checked against ai.google.dev/gemini-api/docs/pricing,
# Oct 2026. Thinking tokens are billed as output tokens on all three. These test calls
# run on the AI Studio FREE tier (no real charge); this is only a paid-tier cost estimate
# so the owner can judge what production usage on Vertex AI would cost.
PRICE_PER_1M = {
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75},  # rate through 31 Dec 2026
}

# A conservative per-call token estimate used only for the pre-flight cost estimate
# (actual counts are measured and reported after the run). An 480x960 JPEG at the
# configured resize settings is a "low" to "medium" resolution image for billing.
ESTIMATED_INPUT_TOKENS_PER_CALL = 450  # image + short system prompt
ESTIMATED_OUTPUT_TOKENS_PER_CALL = 250  # structured JSON + minimal thinking

# 20 images, same proportions as the 30-image set (15:10:5 -> 10:7:3)
SELECTION_COUNTS = {"L1": 10, "L3": 7, "N1": 3}


def select_images(manifest: list) -> list:
    chosen = []
    counts = dict(SELECTION_COUNTS)
    for entry in manifest:
        layout = entry["layout"]
        if counts.get(layout, 0) > 0:
            chosen.append(entry)
            counts[layout] -= 1
    return chosen


def estimate_cost(n_images: int) -> dict:
    total_calls = n_images * len(MODELS)
    per_model = {}
    grand_total = 0.0
    for model in MODELS:
        price = PRICE_PER_1M[model]
        cost_per_call = (
            ESTIMATED_INPUT_TOKENS_PER_CALL / 1_000_000 * price["input"]
            + ESTIMATED_OUTPUT_TOKENS_PER_CALL / 1_000_000 * price["output"]
        )
        model_total = cost_per_call * n_images
        per_model[model] = {"calls": n_images, "estimated_cost_usd": round(model_total, 4)}
        grand_total += model_total
    return {"total_calls": total_calls, "per_model": per_model, "estimated_total_usd": round(grand_total, 4)}


def screen_rejected_correctly(predicted: ExtractionResult) -> bool:
    return predicted.screen_type == "order_offer" and not predicted.trips and predicted.payout_summary is None


def compare_number(pred: Optional[float], truth: Optional[float], tol: float = 0.5) -> Optional[bool]:
    if truth is None:
        return None  # field not applicable to this image; excluded from accuracy denominator
    if pred is None:
        return False
    return abs(pred - truth) <= tol


TRIP_FIELDS = ["base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min"]
PAYOUT_FIELDS = ["total_credited"]


def score_trip_detail(predicted: ExtractionResult, truth: ExtractionResult) -> dict:
    scores = {f: None for f in TRIP_FIELDS}
    if predicted.trips and truth.trips:
        p, t = predicted.trips[0], truth.trips[0]
        for field in TRIP_FIELDS:
            scores[field] = compare_number(getattr(p, field), getattr(t, field))
    else:
        for field in TRIP_FIELDS:
            truth_val = getattr(truth.trips[0], field) if truth.trips else None
            scores[field] = False if truth_val is not None else None
    return scores


def score_payout_summary(predicted: ExtractionResult, truth: ExtractionResult) -> dict:
    scores = {}
    p_summary = predicted.payout_summary
    t_summary = truth.payout_summary
    for field in PAYOUT_FIELDS:
        truth_val = getattr(t_summary, field) if t_summary else None
        pred_val = getattr(p_summary, field) if p_summary else None
        scores[field] = compare_number(pred_val, truth_val)
    return scores


def run(selection: list, settings) -> dict:
    client = get_client(settings)
    results = {}

    for model in MODELS:
        field_checks = []
        rejection_checks = []
        prompt_tokens_total = 0
        output_tokens_total = 0
        thinking_tokens_total = 0
        calls_made_total = 0
        per_image = []

        for entry in selection:
            image_path = ROOT / entry["image"]
            gt_path = ROOT / entry["ground_truth"]
            truth = ExtractionResult.model_validate_json(gt_path.read_text())
            raw = image_path.read_bytes()
            jpeg_bytes = prepare_image(raw, settings.image_max_side_px, settings.image_jpeg_quality)

            outcome = extract_screenshot(client, settings, model, jpeg_bytes)
            calls_made_total += outcome.calls_made
            prompt_tokens_total += outcome.prompt_tokens
            output_tokens_total += outcome.output_tokens
            thinking_tokens_total += outcome.thinking_tokens

            if entry["layout"] == "N1":
                rejection_checks.append(screen_rejected_correctly(outcome.result))
            elif entry["layout"] == "L1":
                field_checks.append(score_trip_detail(outcome.result, truth))
            elif entry["layout"] == "L3":
                field_checks.append(score_payout_summary(outcome.result, truth))

            per_image.append({
                "name": entry["name"],
                "layout": entry["layout"],
                "predicted_screen_type": outcome.result.screen_type,
                "needs_review": outcome.result.needs_review,
                "calls_made": outcome.calls_made,
            })

            time.sleep(1.0)  # pace calls against the AI Studio free-tier rate limit

        correct = sum(1 for checks in field_checks for v in checks.values() if v is True)
        total = sum(1 for checks in field_checks for v in checks.values() if v is not None)
        field_accuracy = round(correct / total, 4) if total else None
        rejection_rate = round(sum(rejection_checks) / len(rejection_checks), 4) if rejection_checks else None

        n_calls = len(selection)
        results[model] = {
            "field_accuracy": field_accuracy,
            "fields_correct": correct,
            "fields_total": total,
            "n1_rejection_rate": rejection_rate,
            "avg_prompt_tokens": round(prompt_tokens_total / n_calls, 1),
            "avg_output_tokens": round(output_tokens_total / n_calls, 1),
            "avg_thinking_tokens": round(thinking_tokens_total / n_calls, 1),
            "total_calls_made": calls_made_total,
            "estimated_cost_usd": round(
                prompt_tokens_total / 1_000_000 * PRICE_PER_1M[model]["input"]
                + output_tokens_total / 1_000_000 * PRICE_PER_1M[model]["output"],
                4,
            ),
            "per_image": per_image,
        }

    return results


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Print the call count and cost estimate only.")
    group.add_argument("--go", action="store_true", help="Owner has said 'go': make the real Gemini calls.")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text())
    selection = select_images(manifest)
    estimate = estimate_cost(len(selection))

    print(f"Selected {len(selection)} images across layouts: "
          f"{ {k: sum(1 for e in selection if e['layout']==k) for k in SELECTION_COUNTS} }")
    print(f"Models: {MODELS}")
    print(f"Total Gemini calls planned: {estimate['total_calls']} "
          f"({len(selection)} images x {len(MODELS)} models, 1 call each; a schema-invalid "
          f"retry would add at most 1 more call per image per model)")
    print("Estimated cost per model (paid-tier prices; these calls run on the AI Studio FREE tier, so actual charge is $0):")
    for model, info in estimate["per_model"].items():
        print(f"  {model}: {info['calls']} calls, ~${info['estimated_cost_usd']}")
    print(f"Estimated total: ~${estimate['estimated_total_usd']} (paid-tier equivalent)")

    if args.dry_run:
        print("\n--dry-run: no Gemini call made. Re-run with --go after the owner says \"go\".")
        return

    settings = get_settings()
    if settings.gemini_backend != "aistudio":
        raise SystemExit("Model selection must run with GEMINI_BACKEND=aistudio (simulated images only).")

    print("\nOwner said \"go\". Calling Gemini now...")
    results = run(selection, settings)
    RESULTS_PATH.write_text(json.dumps(results, indent=2))

    print("\n=== Results ===")
    for model, r in results.items():
        print(f"{model}: field_accuracy={r['field_accuracy']} ({r['fields_correct']}/{r['fields_total']}) "
              f"n1_rejection_rate={r['n1_rejection_rate']} "
              f"avg_tokens(in/out/thinking)={r['avg_prompt_tokens']}/{r['avg_output_tokens']}/{r['avg_thinking_tokens']} "
              f"calls_made={r['total_calls_made']} est_cost=${r['estimated_cost_usd']}")
    print(f"\nFull results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
