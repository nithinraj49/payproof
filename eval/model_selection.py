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

from extraction.extract import ExtractionCallResult, RateLimitError, extract_screenshot
from extraction.image_prep import prepare_image
from extraction.schema import ExtractionResult
from backend.config import get_settings
from backend.gemini_client import get_client

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "eval" / "generated" / "manifest.json"
RESULTS_PATH = ROOT / "eval" / "model_selection_results.json"
PER_CALL_RESULTS_DIR = ROOT / "eval" / "results"

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


def _field_accuracy(checks_list: list) -> dict:
    correct = sum(1 for checks in checks_list for v in checks.values() if v is True)
    total = sum(1 for checks in checks_list for v in checks.values() if v is not None)
    return {"accuracy": round(correct / total, 4) if total else None, "correct": correct, "total": total}


def run(selection: list, settings) -> dict:
    """Stops immediately on the first rate-limit/quota error (never loops retries).
    Per-call results are written to eval/results/{model}/{name}.json as each call
    completes, so completed work survives an early stop."""
    client = get_client(settings)
    results = {}
    calls_completed_overall = 0
    stopped_early = None

    for model in MODELS:
        field_checks_by_layout = {"L1": [], "L3": []}
        rejection_checks = []
        # "new_*" counts only API calls made in THIS run (for this run's cost estimate).
        # "all_*" also includes calls reused from a previous run's cache (for averages/accuracy).
        new_calls_made = 0
        new_prompt_tokens = 0
        new_output_tokens = 0
        all_prompt_tokens = 0
        all_output_tokens = 0
        all_thinking_tokens = 0
        per_image = []
        model_dir = PER_CALL_RESULTS_DIR / model
        model_dir.mkdir(parents=True, exist_ok=True)

        for entry in selection:
            gt_path = ROOT / entry["ground_truth"]
            truth = ExtractionResult.model_validate_json(gt_path.read_text())
            cached_path = model_dir / f"{entry['name']}.json"
            from_cache = cached_path.exists()

            if from_cache:
                cached = json.loads(cached_path.read_text())
                outcome = ExtractionCallResult(
                    result=ExtractionResult.model_validate(cached["predicted"]),
                    calls_made=cached["calls_made"],
                    prompt_tokens=cached["prompt_tokens"],
                    output_tokens=cached["output_tokens"],
                    thinking_tokens=cached["thinking_tokens"],
                )
            else:
                image_path = ROOT / entry["image"]
                raw = image_path.read_bytes()
                jpeg_bytes = prepare_image(raw, settings.image_max_side_px, settings.image_jpeg_quality)
                try:
                    outcome = extract_screenshot(client, settings, model, jpeg_bytes)
                except RateLimitError as exc:
                    stopped_early = {
                        "model": model,
                        "image": entry["name"],
                        "calls_completed_overall": calls_completed_overall,
                        "message": str(exc),
                    }
                    break
                new_calls_made += outcome.calls_made
                calls_completed_overall += outcome.calls_made
                new_prompt_tokens += outcome.prompt_tokens
                new_output_tokens += outcome.output_tokens
                record = {
                    "name": entry["name"],
                    "layout": entry["layout"],
                    "model": model,
                    "predicted": outcome.result.model_dump(),
                    "needs_review": outcome.result.needs_review,
                    "calls_made": outcome.calls_made,
                    "prompt_tokens": outcome.prompt_tokens,
                    "output_tokens": outcome.output_tokens,
                    "thinking_tokens": outcome.thinking_tokens,
                }
                cached_path.write_text(json.dumps(record, indent=2))
                time.sleep(4.5)  # ~13 calls/min: safely under the observed 15 RPM free-tier limit

            all_prompt_tokens += outcome.prompt_tokens
            all_output_tokens += outcome.output_tokens
            all_thinking_tokens += outcome.thinking_tokens

            if entry["layout"] == "N1":
                rejection_checks.append(screen_rejected_correctly(outcome.result))
            elif entry["layout"] == "L1":
                field_checks_by_layout["L1"].append(score_trip_detail(outcome.result, truth))
            elif entry["layout"] == "L3":
                field_checks_by_layout["L3"].append(score_payout_summary(outcome.result, truth))

            per_image.append({
                "name": entry["name"],
                "layout": entry["layout"],
                "predicted_screen_type": outcome.result.screen_type,
                "needs_review": outcome.result.needs_review,
                "calls_made": outcome.calls_made,
                "from_cache": from_cache,
            })

        n_images = max(len(per_image), 1)
        results[model] = {
            "field_accuracy_overall": _field_accuracy(field_checks_by_layout["L1"] + field_checks_by_layout["L3"]),
            "field_accuracy_by_layout": {
                "L1": _field_accuracy(field_checks_by_layout["L1"]),
                "L3": _field_accuracy(field_checks_by_layout["L3"]),
            },
            "n1_rejection_rate": round(sum(rejection_checks) / len(rejection_checks), 4) if rejection_checks else None,
            "avg_prompt_tokens": round(all_prompt_tokens / n_images, 1) if per_image else None,
            "avg_output_tokens": round(all_output_tokens / n_images, 1) if per_image else None,
            "avg_thinking_tokens": round(all_thinking_tokens / n_images, 1) if per_image else None,
            "images_completed": len(per_image),
            "new_calls_made_this_run": new_calls_made,
            "estimated_cost_usd_this_run": round(
                new_prompt_tokens / 1_000_000 * PRICE_PER_1M[model]["input"]
                + new_output_tokens / 1_000_000 * PRICE_PER_1M[model]["output"],
                4,
            ),
            "per_image": per_image,
        }

        if stopped_early:
            break

    return {"results": results, "stopped_early": stopped_early, "calls_completed_overall": calls_completed_overall}


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Print the call count and cost estimate only.")
    group.add_argument("--go", action="store_true", help="Owner has said 'go': make the real Gemini calls.")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text())
    selection = select_images(manifest)

    remaining = {}
    for model in MODELS:
        model_dir = PER_CALL_RESULTS_DIR / model
        done = {p.stem for p in model_dir.glob("*.json")} if model_dir.exists() else set()
        remaining[model] = [e for e in selection if e["name"] not in done]
    total_remaining = sum(len(v) for v in remaining.values())
    estimate = estimate_cost(1)  # per-image, per-model cost; multiplied below per model's remaining count

    print(f"Selected {len(selection)} images across layouts: "
          f"{ {k: sum(1 for e in selection if e['layout']==k) for k in SELECTION_COUNTS} }")
    print(f"Models: {MODELS}")
    for model in MODELS:
        n_done = len(selection) - len(remaining[model])
        print(f"  {model}: {n_done}/{len(selection)} already cached under eval/results/, {len(remaining[model])} remaining")
    print(f"Gemini calls planned THIS run: {total_remaining} "
          f"(already-cached images are skipped and reused, not re-called; a schema-invalid "
          f"retry would add at most 1 more call per remaining image)")
    print("Estimated cost for the calls planned this run (paid-tier prices; these calls run on the AI Studio FREE tier, so actual charge is $0):")
    grand_total = 0.0
    for model, info in estimate["per_model"].items():
        model_total = info["estimated_cost_usd"] * len(remaining[model])
        grand_total += model_total
        print(f"  {model}: {len(remaining[model])} calls, ~${round(model_total, 4)}")
    print(f"Estimated total: ~${round(grand_total, 4)} (paid-tier equivalent)")

    if args.dry_run:
        print("\n--dry-run: no Gemini call made. Re-run with --go after the owner says \"go\".")
        return

    settings = get_settings()
    if settings.gemini_backend != "aistudio":
        raise SystemExit("Model selection must run with GEMINI_BACKEND=aistudio (simulated images only).")

    print("\nOwner said \"go\". Calling Gemini now...")
    print(f"Per-call results will be saved under {PER_CALL_RESULTS_DIR}/<model>/<image>.json")
    outcome = run(selection, settings)
    RESULTS_PATH.write_text(json.dumps(outcome, indent=2))

    print(f"\nTotal Gemini calls completed before stopping: {outcome['calls_completed_overall']}")
    if outcome["stopped_early"]:
        s = outcome["stopped_early"]
        print(f"\n!!! STOPPED EARLY: rate-limit/quota error on model={s['model']} image={s['image']}")
        print(f"!!! API message: {s['message']}")
        print("!!! No retries were looped. Re-run --go later to continue once the limit resets.")

    print("\n=== Results so far ===")
    for model, r in outcome["results"].items():
        print(f"{model}: images_completed={r['images_completed']} new_calls_this_run={r['new_calls_made_this_run']} "
              f"field_accuracy_overall={r['field_accuracy_overall']} "
              f"L1={r['field_accuracy_by_layout']['L1']} L3={r['field_accuracy_by_layout']['L3']} "
              f"n1_rejection_rate={r['n1_rejection_rate']} "
              f"avg_tokens(in/out/thinking)={r['avg_prompt_tokens']}/{r['avg_output_tokens']}/{r['avg_thinking_tokens']} "
              f"est_cost_this_run=${r['estimated_cost_usd_this_run']}")
    print(f"\nFull results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
