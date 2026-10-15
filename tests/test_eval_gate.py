"""eval/run_extraction_eval.py applies the live app's quality gate and the
production safeguards. No Gemini call and no network: a fake client that
fails the test if it is ever called."""
import json
from pathlib import Path

import eval.run_extraction_eval as ev
from backend.config import get_settings

ROOT = Path(__file__).resolve().parent.parent


class ExplodingClient:
    def __getattr__(self, name):
        raise AssertionError("Gemini must not be called for a gate-blocked image")


def _entry(name):
    manifest = json.loads((ROOT / "eval" / "generated" / "manifest.json").read_text())
    return next(e for e in manifest if e["name"] == name)


def test_gate_blocked_hard_image_costs_zero_calls_and_is_recorded_as_gate_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(ev.time, "sleep", lambda s: None)
    settings = get_settings()
    calls = [0]
    summary = ev.evaluate_set(ExplodingClient(), settings, "gemini-3.1-flash-lite", [_entry("H1_009")], calls, 50, 5.0, True)
    assert calls == [0]
    rec = json.loads((tmp_path / "H1_009.json").read_text())
    assert rec["gate_blocked"] is True and rec["calls_made"] == 0 and rec["prompt_tokens"] == 0
    assert rec["predicted"]["needs_review"] is True and rec["predicted"]["trips"] == []
    assert summary["total_failed_calls"] == 0


def test_quality_gate_reason_matches_the_live_app_for_a_standard_image():
    settings = get_settings()
    from extraction.image_prep import prepare_image
    jpeg = prepare_image((ROOT / "eval" / "generated" / "images" / "L1_001.jpg").read_bytes(),
                         settings.image_max_side_px, settings.image_jpeg_quality)
    assert ev.quality_gate_reason(settings, jpeg) is None
