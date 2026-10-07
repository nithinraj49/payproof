"""Phase 2 step B full extraction evaluation, on SIMULATED data only.

Runs the chosen EXTRACTION_MODEL on the Vertex backend against the 30
standard images (L1/L3/N1) and the 10 "hard" images (H1), reported as two
separate tables, and writes eval/RESULTS.md.

Always prints the call count and cost estimate and waits for --go
(REQUIREMENTS.md section 19 rule 9). Never edits .env: set GEMINI_BACKEND and
VERTEX_LOCATION as environment variables for this one command only, e.g.
(PowerShell):
    $env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.run_extraction_eval --dry-run
    $env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.run_extraction_eval --go --pace 15 --cap 30 --stop-on-first-error

Resumable: any image already saved under eval/results/vertex_extraction_eval/
is reused, never re-called, so a stop never wastes a completed call. Every
failed call, fallback (screen_type=other with null fields), or schema failure
surviving the one allowed retry is counted as a MISS in accuracy — never
excluded — and tallied separately per screen type.

--stop-on-first-error: stop the whole run (report exact calls completed) the
moment any single image fails, not just on a systemic rate-limit. Without it,
a systemic rate-limit/quota error still always stops the run; any other
single-image failure is recorded as a miss and the run continues.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from backend.config import get_settings
from backend.gemini_client import get_client
from extraction.extract import RateLimitError, _call_once, _is_rate_limit
from extraction.image_prep import prepare_image
from extraction.schema import ExtractionResult
from eval.model_selection import PRICE_PER_1M

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "eval" / "generated" / "manifest.json"
RESULTS_DIR = ROOT / "eval" / "results" / "vertex_extraction_eval"
RESULTS_MD_PATH = ROOT / "eval" / "RESULTS.md"

DEFAULT_PACE_SECONDS = 3.0
DEFAULT_CALL_CAP = 50
TOLERANCE = 0.5
NEAR_MISS_MAX = 2.0

ESTIMATED_INPUT_TOKENS = 2433  # observed on the 5-image Vertex smoke test
ESTIMATED_OUTPUT_TOKENS = 210

TRIP_FIELDS = ["base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min"]
PAYOUT_FIELDS = ["total_credited"]


class StopOnFirstError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


def load_manifest():
    manifest = json.loads(MANIFEST_PATH.read_text())
    standard = [e for e in manifest if e["layout"] in ("L1", "L3", "N1")]
    hard = [e for e in manifest if e["layout"] == "H1"]
    return standard, hard


def estimate_cost(model: str, n_calls: int) -> float:
    price = PRICE_PER_1M[model]
    return n_calls * (ESTIMATED_INPUT_TOKENS / 1_000_000 * price["input"] + ESTIMATED_OUTPUT_TOKENS / 1_000_000 * price["output"])


def call_with_one_retry(client, settings, model: str, jpeg_bytes: bytes):
    """One call, one retry on schema-invalid output. Raises RateLimitError (systemic)
    or RuntimeError (the image's own failure) on total failure."""
    calls_made = 0
    prompt_tokens = output_tokens = thinking_tokens = 0
    last_exc = None
    for _ in range(2):
        try:
            response, pt, ot, tt = _call_once(client, settings, model, jpeg_bytes)
        except Exception as exc:
            calls_made += 1
            if _is_rate_limit(exc):
                raise RateLimitError(str(exc)) from exc
            last_exc = exc
            continue
        calls_made += 1
        prompt_tokens += pt
        output_tokens += ot
        thinking_tokens += tt
        try:
            result = ExtractionResult.model_validate_json(response.text)
            return result, prompt_tokens, output_tokens, thinking_tokens, calls_made
        except ValidationError as exc:
            last_exc = exc
            continue
    raise RuntimeError(f"{type(last_exc).__name__}: {last_exc}") if last_exc else RuntimeError("unknown failure")


def _status_row(field, pred, truth):
    if pred is None:
        status = "missing"
    else:
        diff = abs(pred - truth)
        if diff <= TOLERANCE:
            status = "correct"
        elif diff <= NEAR_MISS_MAX:
            status = "near_miss"
        else:
            status = "wrong"
    return {"field": field, "pred": pred, "truth": truth, "status": status}


def score_image(predicted: ExtractionResult, truth: ExtractionResult, layout: str) -> list:
    rows = []
    if layout in ("L1", "H1"):
        pred_trip = predicted.trips[0].model_dump() if predicted.trips else {}
        truth_trip = truth.trips[0].model_dump() if truth.trips else {}
        for field in TRIP_FIELDS:
            t = truth_trip.get(field)
            if t is None:
                continue
            rows.append(_status_row(field, pred_trip.get(field), t))
    elif layout == "L3":
        pred_summary = predicted.payout_summary.model_dump() if predicted.payout_summary else {}
        truth_summary = truth.payout_summary.model_dump() if truth.payout_summary else {}
        for field in PAYOUT_FIELDS:
            t = truth_summary.get(field)
            if t is None:
                continue
            rows.append(_status_row(field, pred_summary.get(field), t))
    return rows


def check_n1(predicted: ExtractionResult) -> dict:
    rejected = predicted.screen_type == "order_offer" and not predicted.trips and predicted.payout_summary is None
    leaked_numbers = bool(predicted.trips) or predicted.payout_summary is not None
    return {"rejected": rejected, "leaked_numbers": leaked_numbers}


FALLBACK_RESULT = ExtractionResult(screen_type="other", trips=[], payout_summary=None, needs_review=True,
                                    notes="Gemini call failed; counted as a miss.")


def evaluate_set(client, settings, model: str, entries: list, total_calls_made: list,
                  call_cap: int, pace_seconds: float, stop_on_first_error: bool) -> dict:
    by_field = {}
    by_noise = {}
    n1_results = []
    failed_by_layout = {}
    near_misses = []
    per_image = []

    for entry in entries:
        cached_path = RESULTS_DIR / f"{entry['name']}.json"
        layout = entry["layout"]
        noise = entry["noise"]
        gt = ExtractionResult.model_validate_json((ROOT / entry["ground_truth"]).read_text())

        if cached_path.exists():
            cached = json.loads(cached_path.read_text())
            result = ExtractionResult.model_validate(cached["predicted"])
            failed = cached.get("failed_call", False)
            if failed:
                failed_by_layout[layout] = failed_by_layout.get(layout, 0) + 1
        else:
            if total_calls_made[0] >= call_cap:
                print(f"  !!! Call cap ({call_cap}) reached — stopping before {entry['name']}.")
                break

            raw = (ROOT / entry["image"]).read_bytes()
            jpeg_bytes = prepare_image(raw, settings.image_max_side_px, settings.image_jpeg_quality)
            failed = False
            error_text = None

            try:
                result, prompt_tokens, output_tokens, thinking_tokens, calls_made = call_with_one_retry(client, settings, model, jpeg_bytes)
            except RateLimitError:
                raise  # systemic: caller stops the whole run regardless of the flag
            except Exception as exc:
                failed = True
                error_text = f"{type(exc).__name__}: {exc}"
                result = FALLBACK_RESULT
                prompt_tokens = output_tokens = thinking_tokens = 0
                calls_made = 2
                failed_by_layout[layout] = failed_by_layout.get(layout, 0) + 1

            total_calls_made[0] += calls_made

            record = {
                "name": entry["name"], "layout": layout, "noise": noise, "model": model, "backend": "vertex",
                "predicted": result.model_dump(), "failed_call": failed, "error": error_text,
                "calls_made": calls_made, "prompt_tokens": prompt_tokens, "output_tokens": output_tokens,
                "thinking_tokens": thinking_tokens,
            }
            cached_path.write_text(json.dumps(record, indent=2))

            status_note = f"FAILED ({error_text})" if failed else f"screen_type={result.screen_type}"
            print(f"  {entry['name']} [{layout}/{noise}]: {status_note} calls_made={calls_made} "
                  f"tokens(in/out/thinking)={prompt_tokens}/{output_tokens}/{thinking_tokens}")

            if failed and stop_on_first_error:
                per_image.append({"name": entry["name"], "layout": layout, "noise": noise, "failed": True})
                raise StopOnFirstError(f"{entry['name']}: {error_text}")

            time.sleep(pace_seconds)

        if layout == "N1":
            n1_check = check_n1(result)
            n1_check["name"] = entry["name"]
            n1_check["failed_call"] = failed
            n1_results.append(n1_check)
        else:
            rows = score_image(result, gt, layout)
            for row in rows:
                row.update(name=entry["name"], layout=layout, noise=noise)
                by_field.setdefault(row["field"], {"correct": 0, "total": 0})
                by_field[row["field"]]["total"] += 1
                by_noise.setdefault(noise, {"correct": 0, "total": 0})
                by_noise[noise]["total"] += 1
                if row["status"] == "correct":
                    by_field[row["field"]]["correct"] += 1
                    by_noise[noise]["correct"] += 1
                elif row["status"] == "near_miss":
                    near_misses.append(row)

        per_image.append({"name": entry["name"], "layout": layout, "noise": noise, "failed": failed})

    total_fields = sum(v["total"] for v in by_field.values())
    correct_fields = sum(v["correct"] for v in by_field.values())
    n1_rejected = sum(1 for r in n1_results if r["rejected"])
    n1_leaked = [r["name"] for r in n1_results if r["leaked_numbers"]]

    return {
        "n_images_in_set": len(entries),
        "n_images_scored": len(per_image),
        "field_accuracy_overall": {
            "accuracy": round(correct_fields / total_fields, 4) if total_fields else None,
            "correct": correct_fields, "total": total_fields,
        },
        "by_field": by_field,
        "by_noise": by_noise,
        "near_misses": near_misses,
        "n1_count": len(n1_results),
        "n1_rejection_rate": round(n1_rejected / len(n1_results), 4) if n1_results else None,
        "n1_leaked_numbers": n1_leaked,
        "failed_by_layout": failed_by_layout,
        "total_failed_calls": sum(failed_by_layout.values()),
        "per_image": per_image,
    }


def render_table(name: str, summary: dict) -> str:
    lines = [f"### {name} ({summary['n_images_scored']}/{summary['n_images_in_set']} images scored, SIMULATED data)", ""]
    overall = summary["field_accuracy_overall"]
    lines.append(f"- Overall field accuracy: {overall['accuracy']} ({overall['correct']}/{overall['total']}) — every failed/fallback call counted as a miss, none excluded")
    lines.append(f"- Failed calls (timeout, API error, or schema failure surviving the retry): {summary['total_failed_calls']}"
                 + (f" — by screen type: {summary['failed_by_layout']}" if summary["failed_by_layout"] else ""))
    if summary["n1_count"]:
        lines.append(f"- N1 (order-offer) rejection rate: {summary['n1_rejection_rate']} ({summary['n1_count']} images)")
        if summary["n1_leaked_numbers"]:
            lines.append(f"  - **N1 images that produced trip/payout numbers instead of being cleanly rejected: {summary['n1_leaked_numbers']}**")
        else:
            lines.append("  - No N1 image produced trip or payout numbers.")
    lines.append("")
    lines.append("| Field | Correct/Total | Accuracy |")
    lines.append("|---|---|---|")
    for field, t in summary["by_field"].items():
        acc = round(t["correct"] / t["total"], 4) if t["total"] else None
        lines.append(f"| {field} | {t['correct']}/{t['total']} | {acc} |")
    lines.append("")
    lines.append("| Noise type | Correct/Total | Accuracy |")
    lines.append("|---|---|---|")
    for noise, t in sorted(summary["by_noise"].items()):
        acc = round(t["correct"] / t["total"], 4) if t["total"] else None
        lines.append(f"| {noise} | {t['correct']}/{t['total']} | {acc} |")
    lines.append("")
    if summary["near_misses"]:
        lines.append(f"Near-misses (wrong but within {NEAR_MISS_MAX} of truth):")
        for row in summary["near_misses"]:
            lines.append(f"- {row['name']} [{row['layout']}/{row['noise']}] {row['field']}: predicted={row['pred']} true={row['truth']}")
    else:
        lines.append("No near-misses: every non-correct field was either a failed call or off by more than the near-miss band.")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--go", action="store_true")
    parser.add_argument("--pace", type=float, default=DEFAULT_PACE_SECONDS, help="Seconds between calls.")
    parser.add_argument("--cap", type=int, default=DEFAULT_CALL_CAP, help="Hard cap on new Gemini calls this run, including retries.")
    parser.add_argument("--stop-on-first-error", action="store_true", help="Stop the whole run on any single-image failure, not just a systemic rate-limit.")
    args = parser.parse_args()

    settings = get_settings()
    if settings.gemini_backend != "vertex":
        raise SystemExit(
            'GEMINI_BACKEND is not "vertex". Set it for this command only, e.g. (PowerShell): '
            '$env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.run_extraction_eval --dry-run'
        )

    model = settings.extraction_model
    standard, hard = load_manifest()
    all_entries = standard + hard
    remaining = [e for e in all_entries if not (RESULTS_DIR / f"{e['name']}.json").exists()]
    cost = estimate_cost(model, len(remaining))

    print(f"Backend: vertex, location: {settings.vertex_location}, project: {settings.project_id}, model: {model}")
    print(f"Standard set: {len(standard)} images (L1/L3/N1). Hard set: {len(hard)} images (H1).")
    print(f"Already cached (will be reused, not re-called): {len(all_entries) - len(remaining)}/{len(all_entries)}")
    print(f"Gemini calls planned THIS run: {len(remaining)} (1 each; a schema-invalid retry adds at most 1 more per image)")
    print(f"Cap this run: {args.cap} calls, including retries. Pacing: {args.pace}s between calls. "
          f"stop_on_first_error={args.stop_on_first_error}")
    print(f"Estimated cost (paid-tier, real Vertex AI billing): ~${round(cost, 4)}")
    print("All results are on SIMULATED data (fictional platforms, generated screenshots).")
    print("Every failed/fallback call is counted as a miss, never excluded.")

    if args.dry_run:
        print("\n--dry-run: no Gemini call made. Re-run with --go after the owner says \"go\".")
        return

    print("\nOwner said \"go\". Calling Vertex AI now...")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    client = get_client(settings)
    total_calls_made = [0]

    try:
        print("\n--- Standard set (30 images) ---")
        standard_summary = evaluate_set(client, settings, model, standard, total_calls_made, args.cap, args.pace, args.stop_on_first_error)
        print("\n--- Hard set (10 images) ---")
        hard_summary = evaluate_set(client, settings, model, hard, total_calls_made, args.cap, args.pace, args.stop_on_first_error)
    except (RateLimitError, StopOnFirstError) as exc:
        reason = "systemic rate limit" if isinstance(exc, RateLimitError) else "stop-on-first-error"
        print(f"\n!!! STOPPED ({reason}): {exc}")
        print(f"!!! Total NEW Gemini calls made this run before stopping: {total_calls_made[0]}")
        print("!!! No automatic retry beyond the one allowed, no switch of model/backend/location.")
        return

    print(f"\nTotal NEW Gemini calls made this run: {total_calls_made[0]}")

    md = [
        "# PayProof extraction evaluation results",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        f"Model: `{model}`. Backend: Vertex AI (`VERTEX_LOCATION=global`). "
        "**All data below is simulated (fictional platforms, generated screenshots) — none of it is real gig-platform data.**",
        "",
        render_table("Standard set", standard_summary),
        render_table("Hard set", hard_summary),
    ]
    RESULTS_MD_PATH.write_text("\n".join(md))
    print(f"\nWritten to {RESULTS_MD_PATH}")
    print("\n" + render_table("Standard set", standard_summary))
    print("\n" + render_table("Hard set", hard_summary))


if __name__ == "__main__":
    main()
