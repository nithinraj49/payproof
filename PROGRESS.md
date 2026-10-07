# PayProof progress log

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
- `firebase.json` (Hosting serves `frontend/`, rewrites `/api/**` to Cloud Run service `payproof` in `asia-south1` before the SPA catch-all), `firestore.rules` (a user may read/write only `users/{uid}/**`), `firestore.indexes.json`, `.firebaserc` (default project `payproof-nithin-2026`).
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

### Next — waiting for owner
- **Do NOT run Phase 2 step B (extraction) yet.** Waiting for the owner to confirm the new `GEMINI_API_KEY` is in `.env` and to say "go".
- Also waiting on, from Phase 1 (deploy still pending): owner fills `frontend/firebase-config.js`; confirms Firebase Authentication (Anonymous + Google) enabled; creates a billing budget alert; notes free-trial expiry if applicable; then approves the deploy commands above.

### Resume commands (PowerShell)
```powershell
cd C:\dev\payproof
pip install -r requirements.txt
pytest -q
uvicorn backend.main:app --reload
```
