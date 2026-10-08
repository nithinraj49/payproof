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

### Next
- Finish the hard-tier run: 2 images remaining (`H1_009`, `H1_010`), needs a fresh "go" once Vertex's quota resets (unknown window — try a longer pace or wait).
- Revisit the cascade decision given the hard-tier 0% accuracy finding.
- REQUIREMENTS.md sections 6 and 19 updated (7 Oct 2026) with: a 429 means the request wasn't processed, handle with at most 2 short randomised pauses separate from the schema retry, then a friendly busy message; sample-image results are cached so repeat visitors cost zero Gemini calls.
- Still pending from Phase 1 (deploy not yet run): owner fills `frontend/firebase-config.js`; confirms Firebase Authentication (Anonymous + Google) enabled; creates a billing budget alert; notes free-trial expiry if applicable; then approves the deploy commands in this file.
- Firestore usage-limit counters still need verification against real Firestore (see gap above).

### Deploy review (8 Oct 2026) — found and fixed before approving anything
- **Dockerfile was missing `COPY extraction/ extraction/`**: `backend/main.py` and `backend/extraction_cache.py` both import from `extraction.*`; the deployed container would have crashed on startup with `ModuleNotFoundError`. Fixed. **When `engine/` is added in Phase 3, it needs the same `COPY engine/ engine/` — check every `backend/*.py` import against the Dockerfile's `COPY` list before every deploy, not just the first one** (also noted in ROADMAP.md's Phase 3 section).
- No `.gcloudignore` existed: created one (includes `.gitignore`'s patterns via `#!include:.gitignore`, plus excludes `frontend/`, `tests/`, `eval/`, docs, the `.xlsx` tracker — none of it is needed to build the Cloud Run image). Added `.dockerignore` too, as defense in depth.
- IAM: owner created a dedicated service account `payproof-run@payproof-nithin-2026.iam.gserviceaccount.com` with only `roles/aiplatform.user` and `roles/datastore.user` (replacing reliance on the default compute service account's overly broad `roles/editor`), per REQUIREMENTS.md section 11's least-privilege requirement.
- `firestore.rules` tightened (see Phase 1 section above): a per-user rule would have let a client reset their own usage counters; replaced with a single deny-all rule, since the frontend never uses the Firestore client SDK.
- `EXPLAIN_MODEL` set to `gemini-3.1-flash-lite` on Cloud Run, matching the owner's `.env` and the `EXTRACTION_MODEL` decision (not yet exercised by any Phase 4 code).

### Resume commands (PowerShell)
```powershell
cd C:\dev\payproof
pip install -r requirements.txt
pytest -q
uvicorn backend.main:app --reload
```
