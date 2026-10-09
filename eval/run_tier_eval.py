"""Phase 2 close-out run: the 10 hard-tier (H1) images and the 10 moderate-tier
(M1) images, gemini-3.1-flash-lite only, on the Vertex backend. SIMULATED data.

Per the owner's decision: the gemini-3.5-flash-lite comparison on the hard
tier is skipped -- every hard image is unreadable even to a human, so a
stronger model cannot fix that; see PROGRESS.md.

Uses extraction.extract.extract_screenshot() directly (the real production
path: one call, one retry on schema-invalid output, then the normalizer and
deterministic safeguards from items A and 3 run automatically) so these
numbers are exactly what the deployed app would actually show -- not a
separate analysis pipeline.

Resumable: skips and reuses any image already saved under
eval/results/vertex_extraction_eval/. Any image blocked by the image-quality
gate (extraction/image_quality.py) costs zero Gemini calls.

Always prints the call count and cost estimate and waits for --go. Stops
immediately on any error (API error or schema failure surviving the retry) --
no blind retries, no loop. Hard-capped at --cap calls total.

Usage (PowerShell), GEMINI_BACKEND/VERTEX_LOCATION set for this command only:
    $env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.run_tier_eval --dry-run
    $env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.run_tier_eval --go --pace 15 --cap 25
"""
import argparse
import json
import time
from pathlib import Path

from backend.config import get_settings
from backend.gemini_client import get_client
from extraction.extract import RateLimitError, extract_screenshot
from extraction.image_prep import prepare_image
from extraction.image_quality import check_image_quality
from extraction.schema import ExtractionResult
from eval.model_selection import PRICE_PER_1M

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "eval" / "generated" / "manifest.json"
RESULTS_DIR = ROOT / "eval" / "results" / "vertex_extraction_eval"

MODEL = "gemini-3.1-flash-lite"
TOLERANCE = 0.5
TRIP_FIELDS = ["base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min"]

ESTIMATED_INPUT_TOKENS = 2433
ESTIMATED_OUTPUT_TOKENS = 210


def load_entries(layout: str) -> list:
    manifest = json.loads(MANIFEST_PATH.read_text())
    return [e for e in manifest if e["layout"] == layout]


def classify(pred, truth, needs_review):
    if truth is None:
        return None
    if pred is None:
        return "abstained" if needs_review else "missing_not_flagged"
    return "correct" if abs(pred - truth) <= TOLERANCE else ("wrong_flagged" if needs_review else "confidently_wrong")


def score(result_dict: dict, gt: dict, needs_review: bool) -> dict:
    tally = {"correct": 0, "abstained": 0, "confidently_wrong": 0, "wrong_flagged": 0, "missing_not_flagged": 0}
    pred_trip = result_dict["trips"][0] if result_dict.get("trips") else {}
    gt_trip = gt["trips"][0]
    for f in TRIP_FIELDS:
        outcome = classify(pred_trip.get(f), gt_trip.get(f), needs_review)
        if outcome:
            tally[outcome] += 1
    return tally


def merge(a, b):
    for k in b:
        a[k] = a.get(k, 0) + b[k]
    return a


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--go", action="store_true")
    parser.add_argument("--pace", type=float, default=15.0)
    parser.add_argument("--cap", type=int, default=25)
    args = parser.parse_args()

    settings = get_settings()
    if settings.gemini_backend != "vertex":
        raise SystemExit('GEMINI_BACKEND is not "vertex". Set it for this command only.')

    hard_entries = load_entries("H1")
    moderate_entries = load_entries("M1")
    all_entries = hard_entries + moderate_entries

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    already_done = {p.stem for p in RESULTS_DIR.glob("*.json")}

    plan = []  # (entry, action) action in {"cached", "gate_block", "call"}
    for e in all_entries:
        if e["name"] in already_done:
            plan.append((e, "cached"))
            continue
        raw = (ROOT / e["image"]).read_bytes()
        jpeg_bytes = prepare_image(raw, settings.image_max_side_px, settings.image_jpeg_quality)
        quality = check_image_quality(
            jpeg_bytes, settings.quality_min_short_side_px, settings.quality_min_sharpness,
            settings.quality_min_contrast, settings.quality_min_brightness, settings.quality_max_brightness,
        )
        if not quality.passed:
            plan.append((e, f"gate_block:{quality.reason}"))
        else:
            plan.append((e, "call"))

    n_calls_planned = sum(1 for _, a in plan if a == "call")
    n_cached = sum(1 for _, a in plan if a == "cached")
    n_gate_blocked = sum(1 for _, a in plan if a.startswith("gate_block"))
    price = PRICE_PER_1M[MODEL]
    cost = n_calls_planned * (ESTIMATED_INPUT_TOKENS / 1_000_000 * price["input"] + ESTIMATED_OUTPUT_TOKENS / 1_000_000 * price["output"])

    print(f"Model: {MODEL} (gemini-3.5-flash-lite comparison skipped on hard tier: unreadable, a stronger model can't fix that)")
    print(f"Hard tier: {len(hard_entries)} images. Moderate tier: {len(moderate_entries)} images.")
    print(f"Already cached: {n_cached}. Blocked by quality gate (zero Gemini cost): {n_gate_blocked}.")
    for e, a in plan:
        if a.startswith("gate_block"):
            print(f"  {e['name']}: {a}")
    print(f"Gemini calls planned THIS run: {n_calls_planned} (1 each; a schema-invalid retry adds at most 1 more per image)")
    print(f"Cap: {args.cap} calls total including retries. Pacing: {args.pace}s between calls.")
    print(f"Estimated cost (real Vertex AI billing): ~${round(cost, 4)}")
    print("Labelled simulated data throughout.")

    if args.dry_run:
        print("\n--dry-run: no Gemini call made. Re-run with --go after the owner says \"go\".")
        return

    print("\nOwner said \"go\". Calling Vertex AI now...")
    client = get_client(settings)
    calls_made = 0

    for e, action in plan:
        name = e["name"]
        gt = json.loads((ROOT / e["ground_truth"]).read_text())

        if action == "cached":
            rec = json.loads((RESULTS_DIR / f"{name}.json").read_text())
            result_dict = rec["predicted"]
            needs_review = result_dict.get("needs_review", False)
        elif action.startswith("gate_block"):
            reason = action.split(":", 1)[1]
            result_dict = {"screen_type": "other", "trips": [], "payout_summary": None, "needs_review": True}
            needs_review = True
            record = {"name": name, "layout": e["layout"], "noise": e["noise"], "model": MODEL, "backend": "vertex",
                       "predicted": result_dict, "gate_blocked": True, "gate_reason": reason,
                       "calls_made": 0, "prompt_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
            (RESULTS_DIR / f"{name}.json").write_text(json.dumps(record, indent=2))
            print(f"  {name}: gate-blocked ({reason}), 0 Gemini calls")
        else:  # "call"
            if calls_made >= args.cap:
                print(f"  !!! Cap ({args.cap}) reached -- stopping before {name}.")
                break
            raw = (ROOT / e["image"]).read_bytes()
            jpeg_bytes = prepare_image(raw, settings.image_max_side_px, settings.image_jpeg_quality)
            try:
                outcome = extract_screenshot(client, settings, MODEL, jpeg_bytes)
            except RateLimitError as exc:
                print(f"\n!!! STOPPED: rate-limit/quota error on {name}")
                print(f"!!! API message: {exc}")
                print(f"!!! Gemini calls made before stopping: {calls_made}")
                break
            calls_made += outcome.calls_made
            result_dict = outcome.result.model_dump()
            needs_review = result_dict["needs_review"]
            record = {"name": name, "layout": e["layout"], "noise": e["noise"], "model": MODEL, "backend": "vertex",
                       "predicted": result_dict, "gate_blocked": False,
                       "calls_made": outcome.calls_made, "prompt_tokens": outcome.prompt_tokens,
                       "output_tokens": outcome.output_tokens, "thinking_tokens": outcome.thinking_tokens}
            (RESULTS_DIR / f"{name}.json").write_text(json.dumps(record, indent=2))
            print(f"  {name}: screen_type={result_dict['screen_type']} needs_review={needs_review} "
                  f"calls_made={outcome.calls_made} tokens(in/out/thinking)={outcome.prompt_tokens}/{outcome.output_tokens}/{outcome.thinking_tokens}")
            time.sleep(args.pace)

        # fall through to scoring for cached/gate_block/call (unless we broke out above)

    print(f"\nTotal NEW Gemini calls made this run: {calls_made}")

    # Final report: re-read everything now on disk for both tiers.
    for layout, label in [("H1", "HARD TIER"), ("M1", "MODERATE TIER")]:
        tally = {}
        gate_blocked_count = 0
        for e in load_entries(layout):
            p = RESULTS_DIR / f"{e['name']}.json"
            if not p.exists():
                continue
            rec = json.loads(p.read_text())
            if rec.get("gate_blocked"):
                gate_blocked_count += 1
            gt = json.loads((ROOT / e["ground_truth"]).read_text())
            tally = merge(tally, score(rec["predicted"], gt, rec["predicted"].get("needs_review", False)))
        print(f"\n=== {label} (SIMULATED data) ===")
        print(f"  {tally}")
        print(f"  gate-blocked (zero Gemini cost): {gate_blocked_count}")


if __name__ == "__main__":
    main()
