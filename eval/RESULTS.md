# PayProof extraction evaluation results

Generated 9 Oct 2026. Model: `gemini-3.1-flash-lite`. Backend: Vertex AI (`VERTEX_LOCATION=global`). Numbers reflect the real production pipeline: `extraction/prompt.py`, the response-schema constraint on `low_confidence_fields` (item A), the `normalize_low_confidence_labels` backstop, and `apply_deterministic_safeguards` (item 3) all ran exactly as the deployed app would run them — these are not a separate analysis-only pipeline.

**All data below is simulated** — fictional platforms, generated screenshots from `eval/generate_data.py` with fixed seeds. No real gig-platform data was used anywhere in this evaluation.

**Outcome definitions:**
- **Correct**: predicted value within 0.5 of ground truth.
- **Abstained**: field is `null` and `needs_review=true` — the model (or the image-quality gate) said "I don't know."
- **Wrong, flagged**: a non-null, wrong value, but `needs_review=true` was still set — the model raised a flag but didn't follow through with `null`.
- **Confidently wrong**: a non-null, wrong value with `needs_review=false` — a wrong number with no warning at all. **This is the main safety number.**
- A real order-offer (N1) screen misclassified as another screen type always counts as a miss (`confidently_wrong`), never excluded.

## Standard set (30 images: 15 trip-detail, 10 weekly-payout, 5 order-offer)

| Outcome | Count |
|---|---|
| Correct | 78/78 |
| Abstained | 0/78 |
| Wrong, flagged | 0/78 |
| **Confidently wrong** | **0/78** |

| Field | Correct/Total |
|---|---|
| base_pay | 15/15 |
| total_payout | 15/15 |
| distance_km | 11/11 |
| duration_min | 12/12 |
| incentive | 7/7 |
| tip | 3/3 |
| total_credited | 10/10 |

N1 (order-offer) rejection: 5/5. By noise type (blur, crop, jpeg_low, low_brightness, tilt, none): 100% on every type.

## Moderate set — M1 (10 trip-detail images, each with one mild degradation: smaller font, light blur, mild JPEG compression, or a partial crop of the header only). Confirmed human-readable: 3 images were read digit-by-digit against ground truth before any Gemini call, with an exact match every time.

| Outcome | Count |
|---|---|
| Correct | 37/41 |
| Abstained | 4/41 |
| Wrong, flagged | 0/41 |
| **Confidently wrong** | **0/41** |

| Field | Correct/Total |
|---|---|
| base_pay | 9/10 |
| total_payout | 9/10 |
| distance_km | 6/7 |
| duration_min | 8/8 |
| incentive | 4/4 |
| tip | 1/2 |

Every non-correct field:

| Image | Field | Predicted | True | Outcome |
|---|---|---|---|---|
| M1_004 | base_pay | null | 85.08 | abstained |
| M1_004 | tip | null | 34.27 | abstained |
| M1_004 | total_payout | null | 112.22 | abstained |
| M1_004 | distance_km | null | 5.4 | abstained |

All four are the same image, which hit a transient `ServerError` on the Gemini call (not a reading failure — the model never actually saw this image; `extract_screenshot`'s fallback correctly marked it `needs_review=true`). **On every image the model actually processed, it made zero mistakes.**

## Hard set — H1 (10 trip-detail images, deliberately degraded past human readability: small font + heavy blur + a 4x pixelation round-trip + a crop through the total-payout number). This tier tests whether the app refuses to guess when a human could not read the screen either — it is not a measure of the model's reading skill, because the screens are not readable by anyone.

| Outcome | Count |
|---|---|
| Correct | 0/38 |
| Abstained | 37/38 |
| Wrong, flagged | 1/38 |
| **Confidently wrong** | **0/38** |

| Field | Correct/Total |
|---|---|
| base_pay | 0/10 |
| total_payout | 0/10 |
| distance_km | 0/5 |
| duration_min | 0/9 |
| incentive | 0/2 |
| tip | 0/2 |

`H1_009` was blocked by the image-quality gate (`too_blurry`) before any Gemini call; its 4 relevant fields are counted as abstained via the gate's own fallback, not a model result. The one `wrong_flagged` field is `H1_007`'s `base_pay` (predicted 18.13, true 87.31): the model's numbers are internally self-consistent (`base_pay − its own guessed deduction = its own guessed total_payout`) even though every one of them is fabricated, so the reconciliation safeguard cannot catch it — **only abstaining, or the worker checking the result against their own screenshot (REQUIREMENTS.md FE-3), can catch a self-consistent fabrication.**

## Limitations

- **All results are on generated screenshots from our own simulator** (`eval/generate_data.py`), not real gig-platform screenshots. Real screenshots are completely untested.
- **The image-quality gate's thresholds** (`extraction/image_quality.py`, `QUALITY_MIN_*` in `.env.example`) **are tuned on these same 30 simulated standard images only** (chosen so none of them are blocked) **and are not validated on real screenshots.** They reliably catch very dark, heavily blurred images, but pixelation/JPEG-block artifacts on a bright image can inflate the crude edge-based sharpness measure used here, so the gate does not catch every illegible image (6 of the 10 hard-tier light-mode images pass it despite being unreadable).
- Sample sizes are small (30/10/10 images). None of these numbers should be read as a precision estimate for a production accuracy rate.
- The deterministic safeguards (item 3) and the quality gate reduce "wrong, flagged" and wasted Gemini calls respectively, but neither can catch a self-consistent fabrication (see `H1_007` above) — that failure mode is structural, not a bug to be patched with more code-only checks.
