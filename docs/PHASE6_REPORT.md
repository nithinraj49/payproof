# Phase 6 report: test and harden (15 Oct 2026)

All data in this report is **simulated** (fictional platforms, generated screenshots, throwaway test users). No real-platform image was used anywhere. Bug fixes and checks only; no new features. Nothing was pushed and `v1.0` is not tagged.

## 1. State of the live app

| Item | Value |
|---|---|
| Cloud Run service | `payproof`, region `asia-south1`, revision **`payproof-00013-qbn`** (100% of traffic), service account `payproof-run`, max instances 3, 1 vCPU, 1 GiB, 60 s timeout, **min instances 0** |
| Environment | all 21 variables match `deploy/env.yaml`, no `GEMINI_API_KEY`; Vertex AI at `VERTEX_LOCATION=global`, `gemini-3.1-flash-lite` for extraction and answers |
| Firebase Hosting | last deployed 15 Oct 2026 (after revision 00013), `https://payproof-nithin-2026.web.app`; `Cache-Control: no-cache, no-store, must-revalidate` confirmed on `app.js` |
| Rollback points | tags `live-before-nav`, `live-before-phase6-fixes`, `live-before-batch2`; previous Cloud Run revisions `payproof-00012-6gx`, `payproof-00011-7nt` |
| Pending backend fixes (committed locally, **not deployed**) | one: the evidence-pack header says "N confirmed trip(s)" until the final backend deploy (fixed in `backend/report.py`, test `tests/test_report_header.py`). The final deploy needs the owner's approval. |
| Tests | `pytest -q`: 283 passed. `node --check` on every JS file, `scripts/check_ids.js` and `scripts/check_nav_graph.js`: all pass. |

## 2. Fixes made in Phase 6

- Screen headings (`tabindex="-1"`) never draw a focus outline after a tap or a programmatic focus move; keyboard focus on buttons and inputs is unchanged.
- "Where your money went" chart: the Gross pay bar has its own fill; weekly mode keeps the label "Gross weekly pay".
- New stateless `POST /api/trip-reconciliation` (engine-based, no Firestore write, no Gemini call): the Check screen warns when base pay + incentive + tip - deductions differs from the total payout by more than ₹0.50, with "Fix the numbers" and "Continue anyway"; continuing shows an amber note on Results and in the evidence pack.
- Application logs no longer contain the user id (three log lines changed); a test fails if any logger call references a uid, token or email.
- Money is calculated in `Decimal` and rounded half up (7823 / 40 now shows ₹195.58); the deduction share keeps 4 decimals.
- Data-quality notes are plain words with human numbering and engine amounts, for example "Trip 1: the amounts add up to ₹147.02, but its screenshot says ₹136.65."
- The browser checks file type (PNG, JPEG, WebP) and size (8 MB) before uploading, with the friendly messages from `strings.js` and no network call.
- 16 px spacing around the reconciliation panels and between their two buttons.
- `eval/run_extraction_eval.py` now applies the live quality gate and the production safeguards (it did not before); `eval/production_view.py` shows saved results the way the live app would.
- CLAUDE.md gained a "Deploy policy" section.

## 3. Acceptance table (live API, `https://payproof-nithin-2026.web.app/api`)

Anonymous throwaway users, simulated images only, run before the Decimal change (revision `payproof-00012-6gx`); the checks affected by later changes were re-run on revision 00013 (section 4).

| Scenario | Expected | Actual | Result |
|---|---|---|---|
| A1 | Valid trip table from a simulated image | 200, `trip_detail`, 1 trip, 4 of 4 compared fields match ground truth | PASS |
| A2 | Valid weekly record | `payout_summary`, 2 lines, total ₹9,149.58 (served from the shared sample cache, so no live call) | PASS |
| A3 | Order offer rejected with a reason and no numbers | `order_offer`, 0 trips, no payout summary | PASS |
| A4 | Blurred image: `needs_review` or quality gate | Blocked by the gate ("too blurry"), `needs_review=true`, 0 trips, 0 Gemini calls | PASS |
| A5/A6 | N/A (change signal disabled); `/api/changes` "unavailable" | 200 `status=unavailable`, no computation | PASS (N/A) |
| A7 | One verified ₹ answer, one plain refusal | ₹192 per engaged hour (verified); restaurant question refused without numbers | PASS |
| A8 | Ungrounded number blocked | ₹999.00 blocked, ₹192.00 passes | PASS |
| A9 | Delete removes data, keeps usage counters | removed 7 docs; trips, weeks, costs, answers all 0; usage doc unchanged | PASS |
| A10 | Repeated sample: no second Gemini call | identical body, global counter unchanged (both calls were cache hits) | PASS (weak) |
| A11 | User B cannot read user A's data | 400 on summary and report for B; none of A's figures in any response | PASS |
| A12 | Daily limit: friendly refusal | 429 "You've reached today's limit for this. Please try again tomorrow." on extract and ask, no Gemini call. **Tested the limit check and the refusal, not the counter increments** (the counter was seeded through the Admin SDK). | PASS |
| A13 | One extraction logs one JSON line, token counts only | 3 real extractions gave exactly 3 log lines; keys: timestamp, endpoint, model, prompt/output/thinking tokens, outcome, estimated cost; no image, extracted value or user id | PASS |
| E1 | Spoofed `is_sample` is charged, not cached | user counter 1 to 2, global 2 to 3, not in `sample_cache` | PASS |
| E2 | Weekly reconciliation numbers | gap ₹1,097.00, net payout ₹9,023.00, net earnings ₹7,823.00, ₹30.08/km, per hour ₹195.57 at the time (now ₹195.58 after the Decimal fix) | PASS |
| E3 | Trip reconciliation | computed ₹147.02 vs paid ₹136.65, gap ₹10.37; matching trip not flagged | PASS |
| E4 | Extract then ask, same user, same day | no crash; `questions` went 0 to 1 | PASS |
| E5 | Friendly errors, no 500s | friendly JSON errors (415 text file and PDF, 400 fake JPEG, 413 over 8 MB); **the connection dropped in 2 of about 75 sequences** (see limitations) | **FAIL (intermittent)** |
| E6 | Trip worked example | 128 / 192.00 / 85.33 / 20.00 / 0.0588 | PASS |
| E7 | Weekly worked example | 6,120 / 127.50 / 15.77 / 0.0353 | PASS |
| E8 | Data-quality text for a trip mismatch | was `reconciliation gap > 0.5 on trip(s): [0]`; replaced (section 2) | fixed |

## 4. Regression after the batch deploy (revision `payproof-00013-qbn`, no Gemini calls)

| Check | Expected | Actual | Result |
|---|---|---|---|
| E2 | gap 1,097; net 7,823; 30.08/km; ₹195.58/h; zero gap 0 | 1097.0; 7823.0; 30.08; **195.58**; 0.0 | PASS |
| E3 | flagged 147.02 vs 136.65, gap 10.37 | exactly that; matching not flagged | PASS |
| E5 via Hosting and direct | friendly errors | 415, 400, 413, 415 on both paths | PASS |
| E6 | 128 / 192.00 / 85.33 / 20.00 / 0.0588 | identical | PASS |
| E7 | 6,120 / 127.50 / 15.77 / 0.0353 | identical, no notes | PASS |
| Data-quality text | "Trip 1: the amounts add up to ₹147.02, but its screenshot says ₹136.65." | exactly that, flagged trips = 1 | PASS |
| Evidence-pack wording | plain note, amber warning, no raw wording | note and warning present; header still says "trip(s)" | FAIL, fix pending deploy |

**Final deploy regression (to be filled in after the owner approves the final backend deploy):** E2, E3, E5, E6, E7, data-quality text and the evidence-pack header singular and plural.

## 5. Privacy evidence

| Claim | Evidence |
|---|---|
| No uploaded image is stored in Cloud Storage | The only bucket, `run-sources-payproof-nithin-2026-asia-south1`, holds 13 `.zip` source uploads from deploys. All 13 were opened: 0 image files (only `backend/`, `engine/`, `extraction/`, and later `assets-src/` and `scripts/`). The code imports no storage library and has no file writes; images are handled in memory only (`image_prep.py`, `image_quality.py`). |
| No image is stored in Firestore | A scan of every document (field names and value types only) found no bytes, no string over 600 characters and no encoded image. Collections: `sample_cache` (3 structured extraction results of the curated samples), `usage_global`, and under `users/{id}`: `answers`, `costs`, `trips`, `weeks`, `usage`. |
| No image or personal data in Cloud Run logs | 1,685 entries from the last 7 days: application lines are uvicorn access lines (method, path, status), startup lines, and 56 Gemini-call JSON lines with token counts only. None of the 33 Auth user ids appears; no `/9j/`, `iVBOR`, `base64`, `Bearer`, `eyJ` or extracted value. The words `user_id` and `question` match only as source-code lines inside old traceback text (the fixed KeyError on 11 and 13 Oct). |
| Logs contain only endpoint names, status codes, outcomes, token counts and costs | Gemini-call lines have exactly these keys: timestamp, endpoint, model, prompt_tokens, output_tokens, thinking_tokens, outcome, estimated_cost_usd. A test (`tests/test_logging_privacy.py`) fails if the delete endpoint or any logger call includes the user id. |
| Platform request logs (Cloud Run's own, cannot be removed) | They record the client IP address (`remoteIp`), `userAgent`, `referer`, the request URL (path and query-parameter names such as `mode`), method, status, latency, request and response size, and `serverIp`. No request bodies, no Authorization headers, no tokens. **Wording for the deck: "PayProof's own logs contain no personal data; Google Cloud's automatic request logs may record the visitor's IP address, browser and the page address."** |
| Firestore rules are deny-all | The deployed ruleset (released 8 Oct) is identical to `firestore.rules`: `match /{document=**} { allow read, write: if false; }`. With a real anonymous ID token, five direct Firestore REST attempts (read own usage doc, read global counter, list `sample_cache`, write own usage doc, create a document) all returned HTTP 403 `PERMISSION_DENIED`, and the counter was unchanged. |
| `DELETE /api/data` leaves only the usage counters | Before: answers 1, costs 1, trips 1, usage 1, weeks 1. After: only `usage` (1). Same result in acceptance scenario A9. Usage counters are kept on purpose so a user cannot reset their own limit. |

## 6. Grounding audit

| Check | Result | Evidence |
|---|---|---|
| No LLM or network call in `engine/` | Pass | no `httpx`, `requests`, `google`, `genai`, `firebase` imports under `engine/` |
| Every number shown comes from the API | Pass, with listed presentation-only transforms | The front end only formats API values (`frontend/format.js`) and scales chart bars. Presentation transforms: ×100 for the percentage format (`format.js:59`), `Math.abs` of the reconciliation gap for the amber note (`app.js` Results), bar-length scaling in the chart (`renderMoneyChart`), and the count-up animation, which always ends on the API's own formatted text. User-typed costs are sent to the API unchanged. |
| Tools return engine results only; verifier runs on every draft; one retry; fallback is a refusal | Pass | `backend/qa.py`: tools 99-148, `verify_numbers` 544, `ask_question` 781-844 |
| Wrong number blocked | Pass | ₹199 blocked; 192.50 blocked |
| Rounded number | Pass | ₹192 passes against 192.00; 192.50 blocked |
| Percentages | Pass | 5.88% passes against 0.0588; 6.9% blocked; a bare 588% on a non-ratio field blocked |
| ₹ and `Rs.` | Pass | both parsed; `$` and `€` flagged as wrong currency |
| Indian grouping | Pass | `1,23,456` passes, `1,23,457` blocked, Western `123,456` passes |
| Number words | Pass | "one hundred ninety two" passes, "two hundred" blocked, "nine percent" blocked |
| Dates and counts | Pass | an ungrounded date and a wrong trip count are blocked |
| Non-English numerals | Not built (English only) | Hindi and Tamil digits are read as numbers and blocked (fail safe) |
| Refusal: off-topic (live) | Pass | "I can only answer questions about your gig work pay data." |
| Refusal: advice (live) | Pass | "I cannot provide financial or career advice." |
| Refusal: accusation (live) | Pass | "I can only provide you with the facts about your pay."; no accusation words; deterministic backstop also tested (`fraud`, legal advice flagged) |
| Refusal: prompt injection (live) | Pass | declined to ignore rules or print the system prompt; ₹5,000 not repeated |
| Refusal: missing data (live) | Pass | "not available in your current data", no numbers |
| Refusal: weekly per-trip-hour (live) | Pass | exact sentence: "Your weekly screenshot has no per-trip minutes, so that rate isn't available in weekly mode." |
| Positive control (live) | Pass | "Your net pay per online hour was ₹127.5." (verified) |
| Banned words in copy | Pass | "cheat", "fraud", "proof of", "significant" appear only inside the prohibitions in `backend/qa.py` |
| Q&A unit tests | 92 passed | `tests/test_qa_*`, `tests/test_api_ask.py` |

**Stated limitation (verifier gap):** the verifier checks only numeric values in tool output. A model that quotes an amount from a data-quality note (for example "₹147.02" from a trip-mismatch note) would be treated as ungrounded and the answer replaced by a refusal. This is a safe failure, not a wrong number, and it is not fixed. Also, the live answers say "₹127.5" rather than "₹127.50": the number matches, only the trailing zero differs.

## 7. Evaluation (copied from `eval/RESULTS.md`, "Phase 6 re-run on the final code")

Same 50 simulated images, same model, same extraction code that is deployed; strict and lenient scoring are identical in every table; full tables, the per-field breakdown and the earlier 9 Oct numbers (kept as history) are in `eval/RESULTS.md`.

| Tier | Correct | Silent gap | Abstained | Failed call | Gate-blocked | Wrong, flagged | Confidently wrong |
|---|---|---|---|---|---|---|---|
| Standard (172 fields) | 171 | 1 | 0 | 0 | 0 | 0 | **0** |
| Moderate (61 fields) | 61 | 0 | 0 | 0 | 0 | 0 | **0** |
| Hard, as run (56 fields, raw model output) | 0 | 0 | 33 | 0 | 0 | 23 | **0** |
| Hard, production view (56 fields, gate + safeguards) | 0 | 0 | 29 | 0 | 23 | 4 | **0** |

Order-offer rejection: 5 of 5. The one silent gap is `L3_004` `period_label` (null with `needs_review=false`), the same as on 9 Oct. Image-level and field-level confidently wrong are both 0 on every tier. Standard and moderate are unchanged from 9 Oct; the hard tier changed (the gate now blocks four images, and unreadable-image answers are not perfectly repeatable at temperature 0, for example `Platform Fee` against `Platform fee`). A transient local TLS failure (`CERTIFICATE_VERIFY_FAILED`) stopped the run once; it was not a model result, was not counted, and the one failed-call record was deleted and re-run. A script fault (no gate, no safeguards in `run_extraction_eval.py`) made the run send four gate-blocked images to Gemini; it is fixed and the production view is computed offline.

## 8. Performance (live app, measured from one machine over the public internet, including Hosting)

| Measurement | Runs | Median | Maximum |
|---|---|---|---|
| Extraction (simulated image, one Gemini call) | 3.43 s, 2.69 s, 4.60 s | **3.43 s** | **4.60 s** |
| Answer (one question, one or two Gemini requests) | 2.81, 4.71, 4.91, 4.72, 2.38, 2.48, 2.66 s | **2.81 s** | **4.91 s** |
| Warm API request (`/health` direct / `/api/whoami` via Hosting) | 5 each | 0.42 s / 0.69 s | 0.45 s / 0.97 s |
| **Cold start** (first request after 15+ minutes idle, direct to Cloud Run `/health`) | 2 measured: 8.3 s and 3.85 s (the log shows "Starting new instance" both times; warm requests after the second took 0.30 to 0.34 s) | **about 6 s (range 3.9 to 8.3 s)** | **8.3 s** |

**Recommendation on minimum instances (not changed; for the owner's Friday decision):** the cold start adds roughly 4 to 8 s to the first API call of a visit (the first sample extraction would take about 5 to 9 s instead of about 1 s). One always-on instance (1 vCPU, 1 GiB) costs roughly $7 a month at idle rates, about $5 for 17 Oct to 7 Nov (unverified price). I recommend `--min-instances=1` for the judging window and back to 0 afterwards; it needs its own approval and is not part of the final deploy.

## 9. Gemini spend in Phase 6

| Activity | Calls | Estimated cost |
|---|---|---|
| Acceptance run (Step 2) | 7 | about $0.0037 |
| Evaluation re-run (50 images) | 51 (one allowed retry; four gate-blocked images were also sent because of the script fault) | $0.0472 (from saved token counts) |
| Live refusal questions and latency (6 questions and a control, 3 extractions) | 20 | $0.0076 |
| **Total** | **78** | **about $0.059** (unverified prices) |

## 10. Known limitations

- **Simulated data only.** Real screenshots, including real-platform layouts, are untested.
- **Degraded weekly-payout screens were never tested** (the moderate and hard tiers are trip screens only).
- **The quality-gate thresholds were tuned on simulated data** and are not validated on real screenshots; they catch the four dark hard images but not every unreadable one.
- **Hard-tier repeatability:** answers on unreadable images are not perfectly repeatable at temperature 0 (9 Oct and 15 Oct differ), so hard-tier counts are indicative, not exact.
- **Upload through Firebase Hosting:** a 9 MB upload takes about 25 s through Hosting (median 24 to 27 s, max 32 s) versus about 1 s direct to Cloud Run, and 2 of about 75 test sequences dropped the connection before it reached the app (no entry in the Cloud Run request log; 60 further uploads were clean). The cause is not identified. The browser now rejects files over 8 MB and non-image types before uploading.
- **Verifier gap:** amounts quoted from data-quality notes are treated as ungrounded (safe failure).
- **A plausible wrong date or a self-consistent fabrication cannot be caught by code.** The date is used only after the worker's explicit tap, and the screenshot sits beside the table for checking.
- **Cold start of about 4 to 8 s** (two measurements: 3.85 s and 8.3 s) with minimum instances at 0.
- **Single currency:** notes and the evidence pack use ₹ with Indian grouping; there is no per-user currency.
- **The pay-change signal is disabled** (offline evaluation found no usable estimator); `GET /api/changes` returns "unavailable".
- **English only.** A regional language is future work.
- **The evidence-pack header ("N confirmed trip(s)")** stays until the final backend deploy.
- **Not verified in a real browser:** no browser-automation tool was available. The focus-outline fix, the client-side upload check, the trip reconciliation panel and its spacing, and the demo flow were checked from the code and the served files only. Please rehearse `docs/DEMO.md` once on a phone.
- **Not pushed, not tagged.**

## 11. Files changed since the start of Phase 6 (tag `live-before-phase6-fixes`)

`CLAUDE.md`, `PROGRESS.md`, `backend/main.py`, `backend/report.py`, `docs/DEMO.md`, `docs/PHASE6_REPORT.md`, `engine/earnings.py`, `engine/models.py`, `eval/RESULTS.md`, `eval/full_analysis.py`, `eval/production_view.py`, `eval/run_extraction_eval.py`, `frontend/api.js`, `frontend/app.js`, `frontend/index.html`, `frontend/strings.js`, `frontend/style.css`, `tests/test_api_trip_reconciliation.py`, `tests/test_engine.py`, `tests/test_engine_rounding.py`, `tests/test_eval_gate.py`, `tests/test_logging_privacy.py`, `tests/test_report_header.py`, plus per-image evaluation results under `eval/results/` (the 9 Oct set moved to `history_2026-10-09_vertex_extraction_eval/`, this run in `vertex_extraction_eval/` and `production_view_2026-10-15/`).
