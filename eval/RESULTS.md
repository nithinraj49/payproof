# PayProof extraction evaluation results

Generated 9 Oct 2026. Model: `gemini-3.1-flash-lite`. Backend: Vertex AI (`VERTEX_LOCATION=global`). Numbers reflect the real production pipeline: `extraction/prompt.py`, the response-schema constraint on `low_confidence_fields`, the `normalize_low_confidence_labels` backstop, and `apply_deterministic_safeguards` all ran exactly as the deployed app would run them.

**All data below is simulated** — fictional platforms, generated screenshots from `eval/generate_data.py` with fixed seeds. No real gig-platform data was used anywhere in this evaluation.

**Outcome definitions** (six, each mutually exclusive):
- **Correct**: predicted value matches ground truth within tolerance (see Strict vs lenient below).
- **Silent gap**: the field is `null` and `needs_review=false` — a quiet, unflagged absence. Reported as its own column in every table because a missing field with no warning is a quiet failure, distinct from an honest "I don't know."
- **Abstained**: the field is `null` and `needs_review=true` — the model (or the image-quality gate) said "I don't know" and said so.
- **Failed call**: a transport or server error meant the model never actually read the image at all; the saved result is an infra fallback, not a judgment about the screen. Kept separate from "abstained" because it says nothing about the model's reading ability.
- **Wrong, flagged**: a non-null, wrong value, with `needs_review=true` still set.
- **Confidently wrong**: a non-null, wrong value with `needs_review=false` — a wrong number with no warning at all. **This is the main safety number.**
- A real order-offer (N1) screen misclassified as another screen type always counts as a miss, never excluded.

**Strict vs lenient tolerance:** lenient = within 0.5 for every numeric field (the tolerance used throughout this evaluation so far). Strict = money exact to 2 decimals (±0.005), distance exact to 0.1 km, minutes exact (±0). **Strict and lenient produce identical results on every tier below** — every mistake in this evaluation has been either exact or wildly wrong; there were no borderline near-misses to separate the two tolerances.

`M1_004` was re-run once (9 Oct) after an earlier transient server error; this report uses that real result, which matched ground truth on every field.

## Standard set (30 images: 15 trip-detail, 10 weekly-payout, 5 order-offer)

| Outcome | Count |
|---|---|
| Correct | 175/176 |
| **Silent gap** | **1/176** |
| Abstained | 0/176 |
| Failed call | 0/176 |
| Wrong, flagged | 0/176 |
| **Confidently wrong** | **0/176** |

**The one silent gap:** `L3_004`'s `period_label` came back `null` with `needs_review=false` — a quiet, unflagged miss. This is a newly-scored field (not checked in earlier reports); it means the standard set is no longer a clean 100% once `period_label` and `credited_on` are included.

| Field | Correct/Total | Silent gaps |
|---|---|---|
| base_pay | 15/15 | 0 |
| total_payout | 15/15 | 0 |
| distance_km | 11/11 | 0 |
| duration_min | 12/12 | 0 |
| trip_date | 15/15 | 0 |
| incentive | 7/7 | 0 |
| tip | 3/3 | 0 |
| trip deduction.amount | 7/7 | 0 |
| trip deduction.label | 7/7 | 0 |
| total_credited | 10/10 | 0 |
| period_label | 9/10 | **1** |
| credited_on | 10/10 | 0 |
| weekly line.amount | 22/22 | 0 |
| weekly line.label | 22/22 | 0 |
| weekly deduction.amount | 3/3 | 0 |
| weekly deduction.label | 3/3 | 0 |

N1 (order-offer) rejection: 5/5, strict and lenient identical.

## Moderate set — M1 (10 trip-detail images, each with one mild degradation). Confirmed human-readable: 3 images read digit-by-digit against ground truth before any Gemini call, exact match every time.

| Outcome | Count |
|---|---|
| Correct | 61/61 |
| Silent gap | 0/61 |
| Abstained | 0/61 |
| Failed call | 0/61 |
| Wrong, flagged | 0/61 |
| **Confidently wrong** | **0/61** |

Every field: 100% (base_pay 10/10, total_payout 10/10, distance_km 7/7, duration_min 8/8, trip_date 10/10, incentive 4/4, tip 2/2, deduction.amount 5/5, deduction.label 5/5). **On every readable image, the model made zero mistakes of any kind, with no silent gaps.**

(`M1_004` initially hit a transient `ServerError` and was re-run once with its own cost gate; the number above is the real, re-run result.)

## Hard set — H1 (10 trip-detail images, deliberately degraded past human readability — confirmed by viewing 8 of them myself and being unable to read any number). Tests whether the app refuses to guess, not reading skill.

| Outcome | Count |
|---|---|
| Correct | 2/38 |
| Silent gap | 0/38 |
| Abstained | 27/38 |
| Failed call | 0/38 |
| Gate-blocked (zero Gemini cost) | 7/38 |
| Wrong, flagged | 20/38 |
| **Confidently wrong** | **0/38** |

| Field | Correct/Total |
|---|---|
| base_pay | 0/10 |
| total_payout | 0/10 |
| distance_km | 0/5 |
| duration_min | 0/9 |
| incentive | 0/2 |
| tip | 0/2 |
| trip_date | 0/10 |
| deduction.amount | 0/4 |
| deduction.label | 2/4 |

`H1_009` was blocked by the image-quality gate before any Gemini call; its 7 relevant fields are counted as gate-blocked, not a model result.

**`trip_date` is 0/10 correct, and every wrong one is `wrong_flagged`, not caught by any safeguard.** The plausible-date safeguard (`extraction/extract.py`) only nulls dates outside 2020-01-01..today; it does **not** catch a plausible-but-wrong date. Five hard-tier images show exactly this: the model returned a confident, in-range date from 2023 or 2024 when the true date was in 2026 — close enough to pass the plausibility check, wrong by one to three years. **This means the app must never use an extracted date for any decision — a cost-period boundary, a pay-change comparison, anything — without the worker confirming it first.** This is a structural limit of a plausibility check, not a bug to patch with a narrower date window.

The 2 correct fields are both `deduction.label` matches (the model happened to read a short label correctly even while every number on the same screen was wrong) — a reminder that label legibility and number legibility aren't the same thing on a degraded image.

## Limitations

- **All results are on generated screenshots from our own simulator** (`eval/generate_data.py`), not real gig-platform screenshots. Real screenshots are completely untested.
- **Degraded weekly-payout screens were not tested.** Both the moderate (M1) and hard (H1) difficulty tiers are trip-detail only; no weekly-payout screen has ever been evaluated under blur, low resolution, cropping or any other degradation. The 100% weekly-field numbers above are all from clean, undistorted screens.
- **The image-quality gate's thresholds** (`extraction/image_quality.py`, `QUALITY_MIN_*` in `.env.example`) **are tuned on the 30 simulated standard images only** (chosen so none of them are blocked) **and are not validated on real screenshots.** They reliably catch very dark, heavily blurred images, but pixelation/JPEG-block artifacts on a bright image can inflate the crude edge-based sharpness measure used here, so the gate does not catch every illegible image.
- Sample sizes are small (30/10/10 images). None of these numbers should be read as a precision estimate for a production accuracy rate.
- The deterministic safeguards reduce "wrong, flagged" and wasted Gemini calls, but cannot catch a self-consistent fabrication (`H1_007`'s `base_pay`: a wrong value whose arithmetic still reconciles with the model's own other wrong values) or a plausible-but-wrong date (see `trip_date` above). Both are structural limits, not bugs to be patched with more code-only checks — the client-side screenshot preview (REQUIREMENTS.md FE-3) and worker confirmation are the remaining guards.
