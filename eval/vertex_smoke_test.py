"""Phase 2 step B Vertex smoke test: confirm the chosen extraction model works
on Vertex AI (application default credentials, GEMINI_BACKEND=vertex,
VERTEX_LOCATION=global) and compare its output with the AI Studio results
already on disk from eval/model_selection.py / eval/results/.

Always prints the call count and cost estimate and waits for --go
(REQUIREMENTS.md section 19 rule 9). Never edits .env: set GEMINI_BACKEND and
VERTEX_LOCATION as environment variables for this one command only, e.g.
(PowerShell):
    $env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.vertex_smoke_test --dry-run
    $env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.vertex_smoke_test --go
"""
import argparse
import json
import time
from pathlib import Path

from pydantic import ValidationError

from backend.config import get_settings
from backend.gemini_client import get_client
from extraction.extract import _call_once
from extraction.image_prep import prepare_image
from extraction.schema import ExtractionResult
from eval.model_selection import PRICE_PER_1M

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "eval" / "generated" / "manifest.json"
AISTUDIO_RESULTS_DIR = ROOT / "eval" / "results"
VERTEX_RESULTS_DIR = ROOT / "eval" / "results" / "vertex_smoke"

N_IMAGES = 5
HARD_CALL_CAP = 10
SELECTED_NAMES = ["L1_001", "L1_002", "L3_001", "N1_001", "L1_006"]  # trip, trip, weekly, order-offer, noisy trip

TRIP_FIELDS = ["base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min"]
PAYOUT_FIELDS = ["period_label", "total_credited", "credited_on"]


def diff_fields(vertex_result: dict, aistudio_result: dict) -> list:
    """Field-by-field comparison. Returns a list of (field, vertex_value, aistudio_value, match)."""
    rows = [
        ("screen_type", vertex_result["screen_type"], aistudio_result["screen_type"]),
        ("needs_review", vertex_result["needs_review"], aistudio_result["needs_review"]),
    ]
    if vertex_result["screen_type"] == "trip_detail" or aistudio_result["screen_type"] == "trip_detail":
        v_trip = vertex_result["trips"][0] if vertex_result.get("trips") else {}
        a_trip = aistudio_result["trips"][0] if aistudio_result.get("trips") else {}
        for f in TRIP_FIELDS:
            rows.append((f, v_trip.get(f), a_trip.get(f)))
    if vertex_result["screen_type"] == "payout_summary" or aistudio_result["screen_type"] == "payout_summary":
        v_pay = vertex_result.get("payout_summary") or {}
        a_pay = aistudio_result.get("payout_summary") or {}
        for f in PAYOUT_FIELDS:
            rows.append((f, v_pay.get(f), a_pay.get(f)))
    return [(f, v, a, v == a) for f, v, a in rows]


def estimate_cost(model: str, n_images: int) -> float:
    price = PRICE_PER_1M[model]
    est_input = 450
    est_output = 250
    return n_images * (est_input / 1_000_000 * price["input"] + est_output / 1_000_000 * price["output"])


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--go", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if settings.gemini_backend != "vertex":
        raise SystemExit(
            'GEMINI_BACKEND is not "vertex" in the current environment. '
            'Set it for this command only, e.g. (PowerShell): '
            '$env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.vertex_smoke_test --dry-run'
        )
    if settings.vertex_location != "global":
        print(f'Warning: VERTEX_LOCATION={settings.vertex_location!r}, expected "global" for this model.')

    model = settings.extraction_model
    manifest = {e["name"]: e for e in json.loads(MANIFEST_PATH.read_text())}
    selection = [manifest[name] for name in SELECTED_NAMES if name in manifest][:N_IMAGES]

    cost = estimate_cost(model, len(selection))
    print(f"Backend: vertex, location: {settings.vertex_location}, project: {settings.project_id}")
    print(f"Model: {model}")
    print(f"Images selected: {[e['name'] for e in selection]}")
    print(f"Gemini calls planned: {len(selection)} (1 call each; a schema-invalid retry would add at most 1 more)")
    print(f"Estimated cost (paid-tier, this is real Vertex AI billing): ~${round(cost, 4)}")

    if args.dry_run:
        print("\n--dry-run: no Gemini call made. Re-run with --go after the owner says \"go\".")
        return

    print("\nOwner said \"go\". Calling Vertex AI now...")
    print(f"Hard cap: {HARD_CALL_CAP} Gemini calls total. Stopping at the first error of any kind, no retry, no fallback.")
    VERTEX_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    client = get_client(settings)

    total_calls_made = 0
    comparisons = []
    stopped_early = None

    for entry in selection:
        if total_calls_made >= HARD_CALL_CAP:
            stopped_early = {"reason": "hard_call_cap_reached", "detail": f"{HARD_CALL_CAP} calls"}
            break

        raw = (ROOT / entry["image"]).read_bytes()
        jpeg_bytes = prepare_image(raw, settings.image_max_side_px, settings.image_jpeg_quality)

        try:
            response, prompt_tokens, output_tokens, thinking_tokens = _call_once(client, settings, model, jpeg_bytes)
            total_calls_made += 1
        except Exception as exc:
            total_calls_made += 1
            stopped_early = {
                "reason": "api_error",
                "image": entry["name"],
                "error_type": type(exc).__name__,
                "detail": str(exc),
            }
            break

        try:
            result = ExtractionResult.model_validate_json(response.text)
        except ValidationError as exc:
            stopped_early = {
                "reason": "schema_error",
                "image": entry["name"],
                "error_type": "ValidationError",
                "detail": str(exc),
                "raw_response_text": response.text,
            }
            break

        record = {
            "name": entry["name"],
            "backend": "vertex",
            "model": model,
            "predicted": result.model_dump(),
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "thinking_tokens": thinking_tokens,
        }
        (VERTEX_RESULTS_DIR / f"{entry['name']}.json").write_text(json.dumps(record, indent=2))

        aistudio_path = AISTUDIO_RESULTS_DIR / model / f"{entry['name']}.json"
        aistudio_record = json.loads(aistudio_path.read_text()) if aistudio_path.exists() else None
        field_diff = diff_fields(record["predicted"], aistudio_record["predicted"]) if aistudio_record else None
        all_match = field_diff is not None and all(row[3] for row in field_diff)
        cost = prompt_tokens / 1_000_000 * PRICE_PER_1M[model]["input"] + output_tokens / 1_000_000 * PRICE_PER_1M[model]["output"]

        comparisons.append({
            "name": entry["name"],
            "field_diff": field_diff,
            "all_match": all_match,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "thinking_tokens": thinking_tokens,
            "cost_usd": round(cost, 6),
        })

        print(f"  {entry['name']}: screen_type={result.screen_type} needs_review={result.needs_review} "
              f"tokens(in/out/thinking)={prompt_tokens}/{output_tokens}/{thinking_tokens} "
              f"all_fields_match_aistudio={all_match} est_cost=${round(cost, 6)}")

        time.sleep(5.0)  # pace well clear of any shared per-project rate limit

    print(f"\nTotal Gemini calls made: {total_calls_made}")
    if stopped_early:
        print(f"\n!!! STOPPED: {stopped_early['reason']}")
        for k, v in stopped_early.items():
            if k != "reason":
                print(f"!!!   {k}: {v}")
        print("!!! No automatic switch of model, location or backend. Waiting for instructions.")

    print(f"\nPer-call results written to {VERTEX_RESULTS_DIR}")
    print("\n=== Field-by-field comparison vs AI Studio ===")
    for c in comparisons:
        print(f"\n{c['name']}: all_match={c['all_match']} tokens(in/out/thinking)={c['prompt_tokens']}/{c['output_tokens']}/{c['thinking_tokens']} cost=${c['cost_usd']}")
        if c["field_diff"]:
            for field, v_val, a_val, match in c["field_diff"]:
                marker = "=" if match else "!="
                print(f"    {field}: vertex={v_val!r} {marker} aistudio={a_val!r}")

    n_match = sum(1 for c in comparisons if c["all_match"])
    thinking_values = [c["thinking_tokens"] for c in comparisons]
    print(f"\nSummary: {n_match}/{len(comparisons)} images matched AI Studio on every field.")
    print(f"Thinking tokens per call: {thinking_values} (thinking_level=MINIMAL requested)")
    print(f"Temperature requested: {0 if model in ('gemini-3.1-flash-lite', 'gemini-3.8-flash') else 'not set (ignored by this model)'}")


if __name__ == "__main__":
    main()
