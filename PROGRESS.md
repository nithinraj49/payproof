# PayProof progress log

## Environment and model decisions (current, 7 Oct 2026)

- **Regions are split on purpose.** Cloud Run and Firestore run in `asia-south1` (REQUIREMENTS.md section 0). Vertex AI's Gemini endpoint runs at `VERTEX_LOCATION=global`, **not** `asia-south1` — none of the three candidate models (`gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-3.8-flash`) are available as a regional endpoint there as of Oct 2026 (checked against the official model docs); all three are `global`/`us`/`eu` only. This is a deliberate, confirmed choice, not a placeholder.
- **`EXTRACTION_MODEL=gemini-3.1-flash-lite`** (owner's choice, 7 Oct 2026), picked after a 20-image, 3-model comparison on the AI Studio free tier plus a 5-image Vertex AI smoke test. Confirmed equivalent behaviour on both backends: `thinking_level=MINIMAL` accepted (0 thinking tokens on every call on both backends), structured `response_schema` output validated every time, `temperature=0` accepted without error. `EXPLAIN_MODEL` is not yet chosen (Phase 4 decision).
- **AI Studio free tier is 15 requests/minute per model, per project** (confirmed by hitting it directly — see the model-selection run below). Any script that calls Gemini on the `aistudio` backend paces calls at least 5 seconds apart (`eval/model_selection.py` uses 4.5s).
- Full detail and the raw numbers behind these decisions are in the phase sections below.

## Phase 1: Skeleton and first deploy — in progress (Tue 6 / Wed 7 Oct)

### Done
- Repo structure: `README.md` stub, `.gitignore` extended (service-account JSON patterns, Python/OS junk), `requirements.txt`, `Dockerfile`.
- Verified before coding:
  - Firebase Hosting → Cloud Run rewrite **is** supported in `asia-south1` (current Firebase docs list it explicitly).
  - Vertex AI Gemini models `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-3.8-flash` are **not** available as regional endpoints in `asia-south1` — only `global`, `us` (multi-region), `eu` (multi-region). So `VERTEX_LOCATION` defaults to `global` in `.env.example`, not `asia-south1`. Cloud Run itself still runs in `asia-south1`.
- Backend skeleton: `backend/config.py` (reads all section 20 env vars), `backend/errors.py` (single `{error_code, message, detail?}` JSON error shape), `backend/auth.py` (Firebase ID token verification, user id only ever from the verified token), `backend/gemini_client.py` (one client module switching on `GEMINI_BACKEND`; no Gemini call made yet), `backend/main.py` (`GET /health`, `GET /api/whoami`).
- Tests: `tests/test_main.py` — `/health` returns `{"status": "ok"}`; `/api/whoami` without a token returns 401 with `error_code: missing_token`. No network calls. `pytest -q` passes (2 passed).
- Security note: a live-looking `GEMINI_API_KEY` value briefly appeared in the tracked `.env.example` file (not `.env`) during this session. The owner removed it and was told to rotate/revoke that key in AI Studio. Verify this was done before any commit/push of `.env.example`.

### Decisions
- `requirements.txt` pinned to versions already present in the local environment (checked against PyPI latest, all current for Python 3.13): fastapi 0.141.1, uvicorn 0.53.0, pydantic 2.13.5, python-dotenv 1.2.4, firebase-admin 7.7.0, google-genai 2.28.0, python-multipart 0.0.32, httpx 0.28.1, pytest 9.1.1.
- `VERTEX_LOCATION=global` (see above) instead of `asia-south1`.

- Frontend skeleton: `frontend/index.html` (anonymous sign-in via Firebase modular JS SDK v12.19.0 from CDN, no build step, calls `/api/whoami`), `frontend/firebase-config.js` (placeholder, with instructions on where to copy the non-secret web config from).
- `firebase.json` (Hosting serves `frontend/`, rewrites `/api/**` to Cloud Run service `payproof` in `asia-south1` before the SPA catch-all), `firestore.rules`, `firestore.indexes.json`, `.firebaserc` (default project `payproof-nithin-2026`).
- `firestore.rules` **tightened on 8 Oct 2026** (during deploy review): the original per-user rule (`users/{uid}/{document=**}` readable/writable by that uid) let a signed-in user tamper with their own `users/{uid}/usage/{day}` counters directly via the client SDK, defeating the rate limit. Since the frontend never uses the Firestore client SDK (only Auth; all data goes through the backend's REST API via the Admin SDK, which ignores these rules), the fix is a single `match /{document=**} { allow read, write: if false; }` — no client can read or write anything directly, including usage counters and the (not yet built) shared sample-extraction cache.
- `phase-check` run: 2/2 tests pass; no uncommitted work in Phase 1 files; secrets scan of tracked files clean; `.env` confirmed gitignored.

### Next
- All Phase 1 code items are done. Remaining before `git tag phase-1`: owner fills `frontend/firebase-config.js` with real (non-secret) values, confirms Firebase Authentication (Anonymous + Google) is enabled, creates a billing budget alert, then runs the deploy commands below and verifies on a phone over mobile data.
- Start Phase 2 (simulator-lite and extraction) after that verification.

### Deploy commands (PowerShell) — not run; owner approval required before each

```powershell
# One-time: log in if needed
gcloud auth login
firebase login

# Backend to Cloud Run
gcloud run deploy payproof `
  --source . `
  --region asia-south1 `
  --allow-unauthenticated `
  --max-instances=3 `
  --set-env-vars PROJECT_ID=payproof-nithin-2026,REGION=asia-south1,VERTEX_LOCATION=global,GEMINI_BACKEND=vertex,EXTRACTION_MODEL=gemini-3.5-flash-lite,EXPLAIN_MODEL=gemini-3.5-flash-lite

# Frontend to Firebase Hosting
firebase deploy --only hosting
```

Owner still needs to: confirm Firebase Authentication (Anonymous + Google) is enabled in the console; create a billing budget alert before first deploy; note free-trial expiry date if applicable; fill in `frontend/firebase-config.js`.

## Phase 2 step A: simulator-lite — done (Wed 7 Oct)

### Done
- `extraction/schema.py` exactly as REQUIREMENTS.md section 4.1.
- `eval/sim_config.py`: fixed seed (20261006), fictional platform list, real-platform deny list, all value ranges from section 12.
- `eval/generate_data.py`: renders L1 (trip detail), L3 (weekly payout), N1 (order offer, rejected) as JPEG screenshots with noise (blur, tilt, partial crop, dark mode, JPEG compression, low brightness) and trip_detail variants that omit distance or minutes. Ground truth JSON beside every image is built directly from `extraction.schema.ExtractionResult`, so it always validates. No Gemini calls.
- Font: Noto Sans Regular/Bold v42 downloaded from Google Fonts (fonts.gstatic.com), SIL Open Font License 1.1 — `eval/assets/fonts/LICENSE.txt`.
- Generated and committed 30 images (15 L1, 10 L3, 5 N1) to `eval/generated/` with `manifest.json`; owner reviewed 6 for realism.
- New dependency added: `pillow==12.3.0` (named explicitly in ROADMAP.md's own Phase 2 step A prompt).
- `pytest -q` still passes (2/2, unrelated to this step).

### Decisions
- Image canvas 480x960, teal header bar, generic card layout — no real platform's logo, colours or wording copied.
- 30-image split: 15 L1 / 10 L3 / 5 N1 (L1 weighted highest as "the main per-trip case" per REQUIREMENTS section 12).

### Security note (resolved)
- Earlier in Phase 1, a live `GEMINI_API_KEY` value briefly appeared in tracked `.env.example`. Owner removed it and confirmed the key would be rotated. Re-confirm rotation before Phase 2 step B, since step B is the first step that actually calls Gemini.

## Phase 2 step B: extraction and model selection — in progress (Wed 7 Oct)

### Done
- `extraction/prompt.py` (REQUIREMENTS.md section 6 rules), `extraction/image_prep.py` (resize/JPEG/strip metadata, in memory only), `extraction/extract.py` (one call + at most one retry on invalid JSON only, then `needs_review=true`; a 429/quota error raises `RateLimitError` instead of being retried or swallowed).
- Checked current docs for all three candidate models: pricing confirmed exactly as the owner's unverified figures (`gemini-3.1-flash-lite` $0.25/$1.50 per 1M in/out, `gemini-3.5-flash-lite` $0.30/$2.50, `gemini-3.8-flash` $0.75/$3.75 through 31 Dec 2026, thinking billed as output on all three). `gemini-3.5-flash-lite` ignores custom temperature (not set there); `gemini-3.8-flash` rejects `thinking_level=MINIMAL` (uses `LOW` instead); the other two use `MINIMAL`.
- `tests/test_extraction.py`: 14 tests, all mocked, no network (schema validation, image prep, per-model config, success/retry/fallback, no-retry-on-network-error, no-retry-on-rate-limit). `pytest -q` now **16 passed** (was 2).
- `eval/model_selection.py`: cost-gated (`--dry-run` / `--go`), resumable (skips and reuses any image already saved under `eval/results/<model>/`, so a stop never wastes a completed call), paces calls at 4.5s apart (~13/min, under the observed 15 RPM free-tier limit), stops immediately on the first rate-limit/billing error with no retry loop.

### Model selection run (AI Studio free tier, GEMINI_BACKEND=aistudio, 20 simulated images: 10 L1, 7 L3, 3 N1)
- **Run 1** (old key): stopped at the very first call — HTTP 402, "prepayment credits are depleted" on that AI Studio project. 0 calls made, $0 spent.
- **Run 2** (new free-tier key): completed 20/20 for `gemini-3.1-flash-lite`, then stopped at call 17 of `gemini-3.5-flash-lite` — HTTP 429, free-tier quota is 15 requests/minute/model for that model. 36 calls completed, $0 spent (free tier).
- **Run 3** (resumed, skipped the 36 already-cached calls, 4.5s pacing): completed the remaining 4 images for `gemini-3.5-flash-lite` (20/20) and attempted all 20 for `gemini-3.8-flash` — **every one of the 20 `gemini-3.8-flash` calls failed** (ReadTimeout / ServerError), so it was not retried further (no blind retry loop) and could not be evaluated this session.
- Results: `gemini-3.1-flash-lite` 91.7% field accuracy headline (44/48), but tracing the one wrong image showed it was a dropped call (0 tokens, immediate fallback, not a misread) — genuine accuracy on answered calls was 100% (44/44). `gemini-3.5-flash-lite`: 100% (48/48), 20/20 calls clean. Both: 100% N1 (order-offer) rejection rate (3/3). Avg tokens: 3.1-flash-lite 1360.4 in / 185.7 out / 0.0 thinking (~$0.0006/call); 3.5-flash-lite 1432.0 in / 213.2 out / 0.0 thinking (~$0.001/call). Thinking tokens are 0 for both, confirming `thinking_level=MINIMAL` works.
- Full data: `eval/model_selection_results.json` (summary) and `eval/results/<model>/<image>.json` (every individual call: parsed prediction + token counts, no images, no keys).

**Note on how fallbacks were scored:** of the 60 calls, 1 fallback for `gemini-3.1-flash-lite`, 0 for `gemini-3.5-flash-lite`, 20/20 for `gemini-3.8-flash`. Checked the scoring code directly: a fallback's null fields are scored as misses against a non-null ground truth (not excluded from the denominator) — the 91.7%/100%/0% headline numbers above already account for every fallback as a miss. Only fields where ground truth itself is `None` are excluded (genuinely not applicable to that image).

### Decision
- **`EXTRACTION_MODEL=gemini-3.1-flash-lite`** (owner's choice, 7 Oct 2026): cheapest of the two working candidates, and once the one dropped call is excluded it is exactly as accurate as `gemini-3.5-flash-lite`. `.env.example` updated.
- Cascade (cheap model, retry with a stronger model only on schema/reconciliation failure): **not built**. At ~100% accuracy in this sample there is nothing for a cascade to catch yet; revisit after the Phase 6 full 40-image evaluation if real accuracy turns out lower on noisier/real-world images.
- `gemini-3.8-flash` is set aside, unevaluated, for now: it is also the most expensive of the three, so even a successful evaluation would be unlikely to change the recommendation.

### Accuracy audit and a "hard" difficulty tier
- `eval/analyze_model_selection.py`: re-derives field accuracy from the saved per-call data (no new Gemini calls), confirming the exact tolerance (0.5), which fields count, and zero near-misses on either model on the original 20-image sample — the task was close to trivial whenever the call succeeded, a real ceiling effect.
- `eval/generate_data.py --hard`: added a 10-image `H1` tier (own fixed seed, doesn't touch the original 30) stacking small fonts, heavy blur, a low-resolution round-trip, and a crop through the total-payout row. Generated only; not yet run through Gemini.

### Vertex AI smoke test (GEMINI_BACKEND=vertex, VERTEX_LOCATION=global, application default credentials, 5 images)
- 5/5 calls succeeded, 0 errors, no retries needed. `thinking_level=MINIMAL` respected (0 thinking tokens on every call, same as AI Studio). `response_schema` output validated every time. `temperature=0` accepted without error.
- 4/5 matched the stored AI Studio result exactly; the 5th (`L1_001`) was Vertex succeeding where the AI Studio baseline was itself the known dropped-call fallback — not a Vertex error. Genuine agreement: 5/5.
- Token counts ran higher on Vertex (~2433 input vs AI Studio's ~1360-1432 average) for the same JPEG bytes — plausibly a different default image tiling/resolution; cost per call stayed in the same range (~$0.0007-0.001). Worth watching in the Phase 6 full evaluation.
- `.env` was never edited: `GEMINI_BACKEND`/`VERTEX_LOCATION` were set as PowerShell session variables for those two commands only.
- Results: `eval/results/vertex_smoke/<image>.json`.

### `POST /api/extract`, usage limits, caching — built, partially tested
- `backend/usage_limits.py` (atomic Firestore counters via transaction, defaults from REQUIREMENTS.md section 10), `backend/extraction_cache.py` (in-memory SHA-256 cache, 500-entry FIFO), `backend/main.py` wires them into `POST /api/extract` (content-type/size checks, image prep, cache check, usage-limit check, one extraction call, log token counts only, cache the result).
- Tested: 7 endpoint tests + 4 usage-limit tests, all mocked (Gemini, Firestore, auth), no network. 27/27 passing at the time.
- **Known gap, not yet covered:** the real Firestore transaction code in `check_and_increment` has no test coverage — there is no Firestore emulator in this environment. Only the pure limit-check logic (`check_limits`) and a no-op mock of the whole function are tested. This needs verifying against real Firestore before relying on it in production.

### Full extraction evaluation on Vertex AI (`eval/run_extraction_eval.py`, 38/40 images; GEMINI_BACKEND=vertex, VERTEX_LOCATION=global)
- Vertex AI has its own per-project `429 RESOURCE_EXHAUSTED` quota, separate from the AI Studio free tier's 15 requests/minute/model — hit it twice, at 15 calls (3s pacing) and again at 23 more calls (15s pacing). Stopped immediately both times, no blind retry, no model/backend/region switch. `eval/run_extraction_eval.py` is resumable (skips and reuses any image already saved under `eval/results/vertex_extraction_eval/`) and takes `--pace`, `--cap`, `--stop-on-first-error` so each resume can be tuned without code changes.
- **Standard set: 30/30 complete, 100% field accuracy (73/73), 100% N1 rejection (5/5), 0 failed calls, 0 near-misses.** Every noise type (blur, crop, jpeg_low, low_brightness, tilt, none) scored 100%.
- **Hard set: 8/10 complete (`H1_009`, `H1_010` not yet run), 0% field accuracy (0/30 relevant fields) — a real, important finding, not a bug.** `H1_001` was rejected as `other` ("appears to be a settings screen"), itself a miss since the ground truth is a real trip. The other 7 were classified as `trip_detail` but with **confidently wrong numbers** — e.g. `H1_002` predicted `base_pay=107.5` against a true `47.96`, and order dates drifted to 2023-2024 against a true 2026 date. The model did flag these fields in `low_confidence_fields`, but per the system prompt's own rule ("null when not shown or not fully readable"), it should have returned `null` instead of guessing. This is the ceiling effect from the earlier 20/30-image runs breaking as soon as the images get genuinely hard, and it's an actionable prompt-compliance gap worth addressing before Phase 6, not just a difficulty data point.
- This reopens the cascade question from the model-selection decision (cheap model + retry on a stronger model for low-confidence/failed cases) — worth reconsidering once the full 40-image hard-tier run is complete.
- Labelled throughout as simulated data; results in `eval/results/vertex_extraction_eval/<image>.json`, table in `eval/RESULTS.md` (not yet written — the run was interrupted by the second rate limit before reaching the write step; regenerate after the last 2 hard images are run).

### Next (superseded — see "Phase 2 close-out" below for current status)

### Deploy review (8 Oct 2026) — found and fixed before approving anything
- **Dockerfile was missing `COPY extraction/ extraction/`**: `backend/main.py` and `backend/extraction_cache.py` both import from `extraction.*`; the deployed container would have crashed on startup with `ModuleNotFoundError`. Fixed. **When `engine/` is added in Phase 3, it needs the same `COPY engine/ engine/` — check every `backend/*.py` import against the Dockerfile's `COPY` list before every deploy, not just the first one** (also noted in ROADMAP.md's Phase 3 section).
- No `.gcloudignore` existed: created one (includes `.gitignore`'s patterns via `#!include:.gitignore`, plus excludes `frontend/`, `tests/`, `eval/`, docs, the `.xlsx` tracker — none of it is needed to build the Cloud Run image). Added `.dockerignore` too, as defense in depth.
- IAM: owner created a dedicated service account `payproof-run@payproof-nithin-2026.iam.gserviceaccount.com` with only `roles/aiplatform.user` and `roles/datastore.user` (replacing reliance on the default compute service account's overly broad `roles/editor`), per REQUIREMENTS.md section 11's least-privilege requirement.
- `firestore.rules` tightened (see Phase 1 section above): a per-user rule would have let a client reset their own usage counters; replaced with a single deny-all rule, since the frontend never uses the Firestore client SDK.
- `EXPLAIN_MODEL` set to `gemini-3.1-flash-lite` on Cloud Run, matching the owner's `.env` and the `EXTRACTION_MODEL` decision (not yet exercised by any Phase 4 code).

### First real deploy attempt (8 Oct 2026) — ran Command 1, found a second bug during verification
- `gcloud run deploy` with the command above succeeded on the first try (build, container repo creation, revision, traffic routing all fine). Service URL: `https://payproof-1065840687031.asia-south1.run.app`. `/health` returned `{"status":"ok"}`, `/api/whoami` returned 401 without a token, service account was the dedicated `payproof-run@...` SA as expected, no `GEMINI_API_KEY` present.
- **But dumping the actual environment variables showed only one existed:** `PROJECT_ID` with a garbled value containing the *entire* `--set-env-vars` string (all 14 `KEY=VALUE` pairs run together with spaces instead of being split into 14 separate variables). PowerShell/gcloud on Windows silently mangled the comma-separated list. The other 13 variables, including `GEMINI_BACKEND`, were never set at all — meaning the live service would have silently used the `aistudio` default (empty `GEMINI_API_KEY`) instead of Vertex AI. `/health` and `/api/whoami` passing gave false confidence; neither endpoint touches Gemini config.
- **Fixes, not yet redeployed:**
  1. `deploy/env.yaml` — all 15 Cloud Run environment variables as quoted strings, non-secret only, used with `gcloud run deploy --env-vars-file=deploy/env.yaml` instead of `--set-env-vars` (which replaces *all* variables at once, including clearing the garbled `PROJECT_ID`). Excluded from `.gcloudignore` and `.dockerignore`.
  2. `backend/config.py`: `get_settings()` now refuses to return (raises `RuntimeError`, no secret values in the message) when `K_SERVICE` is set (i.e. running on Cloud Run) but `GEMINI_BACKEND` isn't `"vertex"`, or `PROJECT_ID`/`VERTEX_LOCATION` are empty. `backend/main.py` calls `get_settings()` once at module import time specifically so this check runs at container startup, not lazily on the first request — a misconfigured container now fails to start at all instead of serving broken requests. Local/dev (no `K_SERVICE`) is unaffected; the `aistudio` default still works. 6 new tests in `tests/test_config.py` (mocked environment, no network): local default passes, valid Cloud Run config passes, and three invalid-config cases each raise with no secret leaked into the error message.
  3. `.claude/skills/deploy-check/SKILL.md` updated: always use `--env-vars-file`, never `--set-env-vars`; added a mandatory step to compare live env vars against `deploy/env.yaml` one by one after every future deploy, and an explicit warning not to treat `/health`/`/api/whoami` passing as proof the environment is correct.
- Corrected `gcloud run deploy` command (same service account, `--max-instances=3`, `--allow-unauthenticated`, `--memory=1Gi`, `--timeout=60`, now with `--env-vars-file=deploy/env.yaml`) is ready; **not yet re-run**, waiting for owner approval.

## Phase 2 close-out (9 Oct 2026)

**Deploy confirmed working.** Owner verified Phase 1 live on their phone: `https://payproof-nithin-2026.web.app` signs in anonymously and shows the backend-verified user id. Owner will tag and push `main` themselves. Firestore rules and Hosting are both deployed (Commands 2 and 3 from the deploy review, run and confirmed).

### Accuracy review and safety hardening (items A-E from the owner's review of the 38/40-image Vertex run)

- **A — `low_confidence_fields` constrained + normalized.** `extraction/schema.py` now types it as a `Literal` of the real Trip/PayoutSummary field names (`TripField`, `PayoutField`); `response_schema` enforcement means Gemini can no longer emit a human label ("Base pay") for any new call. `extraction/extract.py:normalize_low_confidence_labels()` is a backstop for any non-compliant output, mapping common aliases to the real name; anything unrecognized triggers a conservative fallback (every money field on that record is nulled, `needs_review` forced true). Regression test uses the exact `H1_006` labels (`"Date"`, `"Base pay"`, `"Platform fee"`, `"Total payout"`) that originally exposed this bug. `REQUIREMENTS.md` section 4.1 kept in sync.
- **B — Deterministic image-quality gate**, `extraction/image_quality.py`: minimum resolution, a sharpness proxy (Pillow `FIND_EDGES` + `ImageStat`), contrast/brightness checks. No new dependency. A failing image never reaches Gemini or the usage-limit counters. Thresholds (`QUALITY_MIN_SHORT_SIDE_PX=300`, `QUALITY_MIN_SHARPNESS=3.9`, `QUALITY_MIN_CONTRAST=10.0`, `QUALITY_MIN_BRIGHTNESS=15.0`, `QUALITY_MAX_BRIGHTNESS=254.0`) are tuned so none of the 30 standard images are blocked; they catch the 4 dark hard-tier images but **not** the 6 light ones, because pixelation/JPEG-block artifacts inflate the crude edge-variance sharpness measure enough to look "sharp" despite being illegible — a real, documented limitation, not validated on real screenshots.
- **C — Offline cascade check**: 0/30 standard images would need a cascade retry; 8/8 hard images would. A cascade costs nothing on clean images and saves nothing on the hardest ones (where it's needed most), since the safeguards already correctly flag nearly every degraded image.
- **D — `REQUIREMENTS.md` FE-3** now specifies a client-side screenshot preview (never uploaded or stored) next to the extracted table, with "Check these numbers against your screenshot" — the final guard against a confident wrong number, since no code-only safeguard can catch a self-consistent fabrication.
- **E — Deterministic safeguards**, `extraction/extract.py:apply_deterministic_safeguards()`, run automatically inside `extract_screenshot()` (the real production path, not a separate pipeline): (a) any `low_confidence_fields` entry becomes null; (b) reconciliation (`base_pay+incentive+tip-deductions` vs `total_payout`, tolerance 0.5) nulls all four money fields on mismatch; (c) a `trip_date` outside 2020-01-01..today becomes null; (d) zero `distance_km`/`duration_min` becomes null. One short prompt addition (item 4): "if you are not sure of a digit, return null ... never estimate."

### Three difficulty tiers, now all generated and evaluated (SIMULATED data)

- **Standard (30, L1/L3/N1):** 78/78 correct, 0 abstained, **0 confidently wrong**, every noise type 100%.
- **Moderate — M1 (10 new images, own `MODERATE_SEED`):** one mild degradation each (smaller font / light blur / mild JPEG / a partial crop that only cuts the header). Confirmed human-readable by reading 3 of them digit-by-digit against ground truth before any Gemini call — exact match every time. Result: 37/41 correct, 4/41 abstained (all the same image, which hit a transient `ServerError`, not a reading failure), **0/41 confidently wrong**. The model made zero actual mistakes on every image it successfully processed.
- **Hard — H1 (10, deliberately beyond human readability — confirmed by viewing 8 of them myself and being unable to read any number):** this tier tests whether the app refuses to guess, not reading skill. 0/38 correct, 37/38 abstained, 1/38 wrong-but-flagged, **0/38 confidently wrong**. `H1_009` blocked by the quality gate (zero Gemini cost). The one surviving wrong field (`H1_007`'s `base_pay`) is a self-consistent fabrication (the model's own numbers reconcile with each other, just not with the real screen) — structurally uncatchable by any arithmetic check, which is exactly why item D's screenshot-preview guard exists.
- **Main safety number across every tier: 0 confidently wrong.** Full tables, per-field breakdown, and an explicit Limitations section in `eval/RESULTS.md`.
- **Known process gap, fixed mid-run:** the first combined hard+moderate run didn't fully honor "stop at the first error" — `extract_screenshot()` swallows a transient `ServerError` into a safe fallback internally (correct for a live backend serving many users) rather than raising, so the eval script's stop-on-error check (which only catches rate limits) never triggered for `M1_004`'s `ServerError`. Caught and disclosed immediately; the result is correctly labelled as an infra artifact, not a model answer.

### Sample-image cache (item 7) and Firestore usage-limit check (item 8)

- `backend/sample_cache.py`: a separate, persistent Firestore cache (`sample_cache/{hash}`) for curated sample images only. `POST /api/extract` takes `is_sample` (default false); when true it uses this shared cache and skips the usage-limit charge entirely (bounded one-time cost regardless of visitor count). Frontend curation of actual sample images is still Phase 5 work — this is the backend plumbing only.
- **Firestore emulator cannot run in this environment** (`firebase emulators:start` fails: no Java installed; not installing new software without asking). `eval/check_firestore_usage_limits.py` is a manual script for the **owner** to run against the real project: exercises the real `check_and_increment()` against obviously-fake throwaway uid/day values, then deletes everything it created. **Not run by me — the real Firestore transaction path remains genuinely untested until the owner runs it.**

### Final evaluation correction round (9 Oct 2026)

- **`M1_004` re-run** (own cost gate, 1 call): the earlier transient `ServerError` was real infra flakiness, not a reading failure — the re-run matched ground truth on every field. Moderate tier is now a clean **61/61 correct, 0 of anything else** (silent gap, abstained, failed call, wrong-flagged, confidently wrong all zero).
- **`eval/full_analysis.py`** (offline, zero Gemini calls) added three things the earlier report didn't have:
  - **Strict vs lenient tolerance**, side by side: identical on every tier. Every mistake in this evaluation has been exact or wildly wrong — never a borderline near-miss.
  - **"Failed call" split out from "abstained"** as its own outcome (a transport/server error means the model never actually read the image — it says nothing about reading ability), and **"silent gap" split out as its own outcome** (`null` with no `needs_review` flag — a quiet, unflagged miss, worse than an honest abstain).
  - **New scoring for deductions, weekly lines, weekly deductions, `trip_date`, and the weekly period fields.** Found `period_start`/`period_end` should **not** be scored: `eval/generate_data.py`'s L3 layout never actually draws them on screen (only `period_label` and `credited_on` are visible) — scoring them would penalize the model for correctly not guessing unseen data. Excluded.
- **New standard-set finding:** `L3_004`'s `period_label` is a **silent gap** — `null` with `needs_review=false`. The standard set is no longer a clean 100% once `period_label`/`credited_on` are scored (175/176 fields correct, 1 silent gap).
- **New hard-tier finding:** `trip_date` is 0/10 correct, every miss `wrong_flagged`. The plausible-date safeguard only rejects dates outside 2020-today; a confident, plausible-but-wrong date (2023/2024 instead of 2026) sails through uncaught. **Conclusion written into `eval/RESULTS.md`: the app must never use an extracted date for any decision without the worker confirming it first** — this is a structural limit of a plausibility check, not a bug to patch with a narrower window.
- **Item 5 — 5xx handling implemented, not just documented.** The written policy (REQUIREMENTS.md section 19 rule 12: 2 short randomised pauses, then a friendly busy message) existed in docs but not in code — a 429 failed with zero pause, and a 5xx wasn't treated as transient at all. `extraction/extract.py` now retries both the same way (`_call_with_transient_retry`, up to 2 pauses of 1-3s) before raising the same `RateLimitError` that `backend/main.py` already turns into a friendly 503. 3 tests added/updated (mocked 5xx included), 61/61 passing.
- `eval/RESULTS.md` regenerated with all of the above: six outcome columns (correct, silent gap, abstained, failed call, wrong-flagged, confidently wrong) in every table, strict/lenient side by side, the `trip_date` conclusion stated plainly, and a new Limitations entry: degraded weekly-payout screens were never tested (M1 and H1 are both trip-detail only).
- **Bottom line, unchanged and reconfirmed: 0 confidently wrong on every tier**, across every outcome category added in this round.

### Next
- Owner: tag and push `main`; run `eval/check_firestore_usage_limits.py` against the real project when convenient.
- Not started: Phase 5's actual sample-image curation (`frontend/samples/`), degraded weekly-screen testing (noted as a limitation above), `/api/trips`/`/api/weeks`/etc. endpoints (Phase 3), the cascade question (revisit if real-world accuracy looks different from this simulated data).
- **Phase 3 not started — waiting for the owner to say go.**

### Resume commands (PowerShell)
```powershell
cd C:\dev\payproof
pip install -r requirements.txt
pytest -q
uvicorn backend.main:app --reload
```
