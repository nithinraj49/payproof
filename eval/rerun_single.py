"""Re-run exactly one named image through the real production pipeline
(extraction.extract.extract_screenshot), for cases like M1_004 where the
first attempt hit a transient error and the saved result is an infra
artifact rather than a genuine model answer.

Always prints the call count (1) and cost estimate and waits for --go.
GEMINI_BACKEND/VERTEX_LOCATION must already be set as environment variables
for this command only (never edits .env).

Usage (PowerShell):
    $env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.rerun_single --name M1_004 --dry-run
    $env:GEMINI_BACKEND = "vertex"; $env:VERTEX_LOCATION = "global"; python -m eval.rerun_single --name M1_004 --go
"""
import argparse
import json
from pathlib import Path

from backend.config import get_settings
from backend.gemini_client import get_client
from extraction.extract import RateLimitError, extract_screenshot
from extraction.image_prep import prepare_image
from eval.model_selection import PRICE_PER_1M

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "eval" / "generated" / "manifest.json"
RESULTS_DIR = ROOT / "eval" / "results" / "vertex_extraction_eval"

ESTIMATED_INPUT_TOKENS = 2600
ESTIMATED_OUTPUT_TOKENS = 220


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--go", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if settings.gemini_backend != "vertex":
        raise SystemExit('GEMINI_BACKEND is not "vertex". Set it for this command only.')

    manifest = {e["name"]: e for e in json.loads(MANIFEST_PATH.read_text())}
    entry = manifest[args.name]
    model = settings.extraction_model
    price = PRICE_PER_1M[model]
    cost = ESTIMATED_INPUT_TOKENS / 1_000_000 * price["input"] + ESTIMATED_OUTPUT_TOKENS / 1_000_000 * price["output"]

    print(f"Re-running {args.name} only. Model: {model}. Backend: vertex, location: {settings.vertex_location}")
    print(f"Gemini calls planned: 1 (a schema-invalid retry would add at most 1 more)")
    print(f"Estimated cost (real Vertex AI billing): ~${round(cost, 5)}")
    print("Simulated data.")

    if args.dry_run:
        print("\n--dry-run: no Gemini call made.")
        return

    print("\nOwner said \"go\". Calling Vertex AI now...")
    client = get_client(settings)
    raw = (ROOT / entry["image"]).read_bytes()
    jpeg_bytes = prepare_image(raw, settings.image_max_side_px, settings.image_jpeg_quality)

    try:
        outcome = extract_screenshot(client, settings, model, jpeg_bytes)
    except RateLimitError as exc:
        print(f"\n!!! STOPPED: rate-limit/quota error: {exc}")
        return

    result_dict = outcome.result.model_dump()
    record = {
        "name": args.name, "layout": entry["layout"], "noise": entry["noise"], "model": model, "backend": "vertex",
        "predicted": result_dict, "gate_blocked": False,
        "calls_made": outcome.calls_made, "prompt_tokens": outcome.prompt_tokens,
        "output_tokens": outcome.output_tokens, "thinking_tokens": outcome.thinking_tokens,
    }
    (RESULTS_DIR / f"{args.name}.json").write_text(json.dumps(record, indent=2))

    print(f"\nResult: screen_type={result_dict['screen_type']} needs_review={result_dict['needs_review']}")
    print(f"Notes: {result_dict.get('notes')!r}")
    print(f"Trips: {result_dict.get('trips')}")
    print(f"Tokens (in/out/thinking): {outcome.prompt_tokens}/{outcome.output_tokens}/{outcome.thinking_tokens}")
    print(f"\nSaved to {RESULTS_DIR / f'{args.name}.json'}")


if __name__ == "__main__":
    main()
