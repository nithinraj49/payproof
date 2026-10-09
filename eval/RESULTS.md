# PayProof extraction evaluation results

Generated 9 Oct 2026, corrected 9 Oct 2026. Model: `gemini-3.1-flash-lite`. Backend: Vertex AI (`VERTEX_LOCATION=global`). Numbers reflect the real production pipeline: `extraction/prompt.py`, the response-schema constraint on `low_confidence_fields`, the `normalize_low_confidence_labels` backstop, and `apply_deterministic_safeguards` all ran exactly as the deployed app would run them.

**All data below is simulated** — fictional platforms, generated screenshots from `eval/generate_data.py` with fixed seeds. No real gig-platform data was used anywhere in this evaluation.

**Correction note:** an earlier version of this file had two reconciliation bugs, found during review: the hard set's outcome table said "/38" (a stale denominator from before `trip_date` and deduction scoring were added; the real total is 56) and the standard set's header number (176, itself mistakenly written as "175/176") didn't match its own per-field rows (172), because N1's 5 order-offer rejection judgments were being folded into the same total even though N1 has no scorable "field" — it's one judgment per image. Both are fixed below: **every table's outcome counts now sum exactly to its stated denominator**, and N1 is reported in its own line, never blended into the field-level table.

**Outcome definitions** (six, mutually exclusive, apply to one scored field each; N1's rejection judgment is scored separately, see below):
- **Correct**: predicted value matches ground truth within tolerance (see Strict vs lenient).
- **Silent gap**: the field is `null` and `needs_review=false` — a quiet, unflagged absence.
- **Abstained**: the field is `null` and `needs_review=true` — the model (or the image-quality gate) said "I don't know" and said so.
- **Failed call**: a transport or server error meant the model never actually read the image; the saved result is an infra fallback, not a judgment about the screen.
- **Wrong, flagged**: a non-null, wrong value, with the image's overall `needs_review=true`. See "Field-level flag breakdown" below for whether the specific field was individually listed.
- **Confidently wrong**: a non-null, wrong value with the image's overall `needs_review=false` — a wrong number with no warning at all anywhere on that screen. **This is the main safety number, defined at the image level** (see note below for the field-level figure alongside it).

**Strict vs lenient tolerance**, side by side: lenient = within 0.5 for every numeric field. Strict = money exact to 2 decimals (±0.005), distance exact to 0.1 km, minutes exact (±0). **Identical on every tier** — every mistake in this evaluation has been exact or wildly wrong, never a borderline near-miss.

`M1_004` was re-run once (9 Oct) after an earlier transient server error; this report uses that real result, which matched ground truth on every field.

## Standard set (30 images: 15 trip-detail, 10 weekly-payout, 5 order-offer)

**Field-level table (172 fields; N1's 5 images are not fields and are reported separately below):**

| Outcome | Lenient | Strict |
|---|---|---|
| Correct | 171/172 | 171/172 |
| Silent gap | 1/172 | 1/172 |
| Abstained | 0/172 | 0/172 |
| Failed call | 0/172 | 0/172 |
| Wrong, flagged | 0/172 | 0/172 |
| Confidently wrong | 0/172 | 0/172 |
| **Sum check** | **172/172** ✓ | **172/172** ✓ |

**The one silent gap:** `L3_004`'s `period_label` came back `null` with `needs_review=false` — a quiet, unflagged miss.

| Field | Correct/Total |
|---|---|
| base_pay | 15/15 |
| total_payout | 15/15 |
| distance_km | 11/11 |
| duration_min | 12/12 |
| trip_date | 15/15 |
| incentive | 7/7 |
| tip | 3/3 |
| trip deduction.amount | 7/7 |
| trip deduction.label | 7/7 |
| total_credited | 10/10 |
| period_label | 9/10 |
| credited_on | 10/10 |
| weekly line.amount | 22/22 |
| weekly line.label | 22/22 |
| weekly deduction.amount | 3/3 |
| weekly deduction.label | 3/3 |
| **Sum check** | **171/172** ✓ |

**N1 (order-offer rejection, 5 images — a single image-level judgment each, not a field, reported here on its own):** 5/5 correct (strict and lenient identical; N1 has no numeric tolerance to apply).

## Moderate set — M1 (10 trip-detail images, each with one mild degradation). Confirmed human-readable: 3 images read digit-by-digit against ground truth before any Gemini call, exact match every time.

| Outcome | Lenient | Strict |
|---|---|---|
| Correct | 61/61 | 61/61 |
| Silent gap | 0/61 | 0/61 |
| Abstained | 0/61 | 0/61 |
| Failed call | 0/61 | 0/61 |
| Wrong, flagged | 0/61 | 0/61 |
| Confidently wrong | 0/61 | 0/61 |
| **Sum check** | **61/61** ✓ | **61/61** ✓ |

Every field: 100% (base_pay 10/10, total_payout 10/10, distance_km 7/7, duration_min 8/8, trip_date 10/10, incentive 4/4, tip 2/2, deduction.amount 5/5, deduction.label 5/5). No N1 images in this tier. **On every readable image, the model made zero mistakes of any kind, with no silent gaps.**

(`M1_004` initially hit a transient `ServerError` and was re-run once with its own cost gate; the number above is the real, re-run result.)

## Hard set — H1 (10 trip-detail images, deliberately degraded past human readability — confirmed by viewing 8 of them myself and being unable to read any number). Tests whether the app refuses to guess, not reading skill. No N1 images in this tier.

| Outcome | Lenient | Strict |
|---|---|---|
| Correct | 2/56 | 2/56 |
| Silent gap | 0/56 | 0/56 |
| Abstained | 27/56 | 27/56 |
| Failed call | 0/56 | 0/56 |
| Gate-blocked (zero Gemini cost) | 7/56 | 7/56 |
| Wrong, flagged | 20/56 | 20/56 |
| Confidently wrong | 0/56 | 0/56 |
| **Sum check** | **56/56** ✓ | **56/56** ✓ |

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
| **Sum check** | **2/56** ✓ |

`H1_009` was blocked by the image-quality gate before any Gemini call; its 7 relevant fields are counted as gate-blocked, not a model result.

**`trip_date` is 0/10 correct, every miss `wrong_flagged`.** The plausible-date safeguard only nulls dates outside 2020-01-01..today; it does **not** catch a plausible-but-wrong date. Five hard-tier images show exactly this: a confident, in-range date from 2023 or 2024 when the true date was 2026. **The app must never use an extracted date for any decision — a cost-period boundary, a pay-change comparison, anything — without the worker confirming it first.** (Now written into REQUIREMENTS.md FE-3.)

### Field-level flag breakdown (the 20 hard-tier "wrong, flagged" values)

"Wrong, flagged" has so far meant the *image's* `needs_review=true`, not that the *specific wrong field* was individually listed in `low_confidence_fields`. Checked field-by-field for all three tiers:

| Tier | Individually flagged | Image-level flag only | No per-field flag exists* | Total wrong-flagged |
|---|---|---|---|---|
| Standard | 0 | 0 | 0 | 0 (no wrong-flagged values exist) |
| Moderate | 0 | 0 | 0 | 0 (no wrong-flagged values exist) |
| **Hard** | **12** | **6** | **2** | **20** |

\*Deduction amounts/labels have no individual field name in the schema to list in `low_confidence_fields` at all — the model can only flag the whole trip, not "this specific deduction."

**Honest answer to "what share would NOT be individually highlighted in a UI that only highlights listed cells": 8 of 20 (40%).** Those 6 "image-level only" plus 2 "no per-field flag exists" values would show as plain, unhighlighted cells next to a correct-looking neighbor, in a UI design that only highlights the cells named in `low_confidence_fields`. **This is exactly why REQUIREMENTS.md FE-3 now requires a prominent banner and treating every cell as unconfirmed when `needs_review` is true, instead of relying on cell-level highlighting alone.**

### "0 confidently wrong" — image-level vs field-level

Every "confidently wrong" count above (0 on every tier) is defined **at the image level**: a wrong value where the whole screen's `needs_review=false`. The field-level flag breakdown above answers a related but different question — among values that *are* wrong on an already-flagged screen, how many are individually called out. Both are true at once: **0 wrong values anywhere appeared on a screen with no warning at all, but on the hard tier, 40% of wrong values would still look like ordinary, unhighlighted cells if the UI trusted cell-level highlighting instead of the image-level banner.**

## Limitations

- **All results are on generated screenshots from our own simulator** (`eval/generate_data.py`), not real gig-platform screenshots. Real screenshots are completely untested.
- **Degraded weekly-payout screens were not tested.** Both the moderate (M1) and hard (H1) difficulty tiers are trip-detail only; no weekly-payout screen has ever been evaluated under blur, low resolution, cropping or any other degradation. The 100% weekly-field numbers above are all from clean, undistorted screens.
- **The image-quality gate's thresholds** (`extraction/image_quality.py`, `QUALITY_MIN_*` in `.env.example`) **are tuned on the 30 simulated standard images only** (chosen so none of them are blocked) **and are not validated on real screenshots.**
- Sample sizes are small (30/10/10 images). None of these numbers should be read as a precision estimate for a production accuracy rate.
- The deterministic safeguards cannot catch a self-consistent fabrication (`H1_007`'s `base_pay`: wrong but internally reconciles with the model's other wrong values) or a plausible-but-wrong date. Both are structural limits — the client-side screenshot preview and the FE-3 banner/per-cell-confirmation requirement (REQUIREMENTS.md) are the remaining guards, not more code-only checks.
