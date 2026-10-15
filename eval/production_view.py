"""Offline "production view" of saved evaluation results. NO Gemini call.

Takes the per-image records saved by run_extraction_eval.py / run_tier_eval.py
(eval/results/vertex_extraction_eval/) and re-applies, exactly as the live app
does, (1) the deterministic quality gate, then (2) the label normalizer and the
deterministic safeguards (extraction.extract). The result is written to a new
folder with the same record shape, so `eval.full_analysis` can score it:

    python -m eval.production_view
    $env:PAYPROOF_EVAL_RESULTS_DIR = "eval/results/production_view_2026-10-15"; python -m eval.full_analysis

Why it exists: an early version of run_extraction_eval.py called the model
directly, without the gate, the normalizer or the safeguards, so its "as run"
numbers are the raw model output. This shows what the deployed app would show
for the same raw output. Simulated data only.
"""
import json
import sys
from pathlib import Path

from backend.config import get_settings
from eval.run_extraction_eval import quality_gate_reason
from extraction.extract import apply_deterministic_safeguards, normalize_low_confidence_labels
from extraction.image_prep import prepare_image
from extraction.image_quality import QUALITY_MESSAGES
from extraction.schema import ExtractionResult

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "eval" / "results" / "vertex_extraction_eval"
DST = ROOT / "eval" / "results" / "production_view_2026-10-15"
MANIFEST = {e["name"]: e for e in json.loads((ROOT / "eval" / "generated" / "manifest.json").read_text())}


def to_production(rec: dict, settings) -> dict:
    entry = MANIFEST[rec["name"]]
    out = dict(rec)
    out["predicted_raw"] = rec["predicted"]
    jpeg = prepare_image((ROOT / entry["image"]).read_bytes(), settings.image_max_side_px, settings.image_jpeg_quality)
    reason = quality_gate_reason(settings, jpeg)
    if reason is not None:
        blocked = ExtractionResult(screen_type="other", trips=[], payout_summary=None,
                                   needs_review=True, notes=QUALITY_MESSAGES[reason])
        out.update(predicted=blocked.model_dump(), gate_blocked=True, gate_reason=reason, failed_call=False)
        return out
    if rec.get("failed_call"):
        return out  # an infrastructure fallback: nothing to post-process
    data = normalize_low_confidence_labels(dict(rec["predicted"]))
    result = apply_deterministic_safeguards(ExtractionResult.model_validate(data))
    out.update(predicted=result.model_dump(), gate_blocked=False)
    return out


def main():
    settings = get_settings()
    DST.mkdir(parents=True, exist_ok=True)
    n = gated = changed = 0
    for p in sorted(SRC.glob("*.json")):
        rec = json.loads(p.read_text())
        prod = to_production(rec, settings)
        (DST / p.name).write_text(json.dumps(prod, indent=2))
        n += 1
        gated += bool(prod.get("gate_blocked"))
        changed += prod["predicted"] != rec["predicted"]
    print(f"{n} records -> {DST}")
    print(f"gate-blocked in production: {gated} | records whose answer changed after gate + safeguards: {changed}")
    print("No Gemini call was made.")


if __name__ == "__main__":
    sys.exit(main())
