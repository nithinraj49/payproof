# PayProof: build roadmap for Claude Code (v2, from 5 Oct 2026)

> Put this next to `CLAUDE.md` and `REQUIREMENTS.md` in the root of the NEW project folder. `REQUIREMENTS.md` says WHAT to build; this file says in WHAT ORDER, with a paste-ready prompt per phase.
> Today is 5 Oct. Submission closes 18 Oct, 11:59 PM IST; we submit on 17 Oct. That leaves 12 days, so the schedule is tight and the work runs in parallel on four tracks.
> Placeholders: `[PROJECT_ID]`, `[REGION]`, `[GITHUB_USERNAME]`, `[LANG_1]`, `[LANG_2]`.

## How to work with Claude Code

1. Open a terminal in the project folder and run `claude`.
2. Paste ONE prompt at a time. Review, run `pytest` and the "You verify" items, then tag: `git tag phase-N && git push --tags`.
3. Use the skills named in each phase (`phase-check` at the end of every phase).
4. If Claude Code proposes anything outside `REQUIREMENTS.md` (a new library, a new service), say no unless the phase needs it.
5. If a phase runs late, use the cut list at the bottom. Never cut evaluation, the number verifier, or the live link.

## The four tracks (assign one person each)

| Track | Owner | Work | Works in |
|---|---|---|---|
| A: backend and AI | Nithin (suggested) | Skeleton, deployment, extraction, engine, Q&A, verifier, quotas | `backend/ engine/ extraction/ tests/` |
| B: front end | [PERSON] | The screens, sample mode, language switcher, evidence-pack styling | `frontend/` |
| C: data and evaluation | [PERSON] | Simulator, labelled data, curated samples, eval scripts, results | `eval/ frontend/samples/` |
| D: research and submission | [PERSON] | Worker interviews, deck, video, README and docs, form text | `docs/ README.md` |

Each person runs their own Claude Code on their own branch, opens a pull request into `main`, and runs `phase-check` before merging. The data contracts and API table in `REQUIREMENTS.md` are the interface, so tracks can work without waiting for each other.

## Dates and gates

| Date | Gate | Rule |
|---|---|---|
| 6 Oct | Skeleton live | Public Hosting URL reaches Cloud Run with sign-in working |
| **8 Oct** | **Extraction check** | First accuracy table on at least 20 simulated images, including weekly and rejected screens. If field accuracy is poor (suggested bar: below 80%), shrink to 2 layouts and 2 languages before going on |
| 11 Oct | Team formed | Already true on the portal; confirm every member still sees the team |
| 11 Oct | Listen decision | Build the optional text-to-speech button only if Phases 3 and 4 are done |
| **14 Oct** | **Feature freeze** | Tag `v1.0`. After this: bug fixes, evaluation, deck, video only |
| 16 Oct | Form drafted | All six form items ready |
| **17 Oct** | **Submit** | 18 Oct is buffer only |

---

## Phase 0: Pre-flight (5 Oct, about 2 hours, Track A, not Claude Code)

- [ ] Install Python 3.11+, git, Node.js, `gcloud`, `firebase-tools` (`npm install -g firebase-tools`), Claude Code
- [ ] `gcloud auth login`, `gcloud auth application-default login`, `firebase login`
- [ ] Create Google Cloud project `[PROJECT_ID]`; link billing; claim the hackathon credits; set a billing budget alert
- [ ] Enable APIs: `gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com firestore.googleapis.com firebase.googleapis.com identitytoolkit.googleapis.com`
- [ ] In the Firebase console add Firebase to the SAME project; enable Authentication (Anonymous and Google) and create Firestore in native mode in `[REGION]`
- [ ] Create a NEW public GitHub repo `payproof` (MIT); clone it; copy in `CLAUDE.md`, `REQUIREMENTS.md`, `ROADMAP.md` and the `.claude/skills/` folder from the skills zip
- [ ] Commit and push; invite the other three teammates as collaborators

---

## Phase 1: Skeleton and first deploy (5 to 6 Oct, Track A)

**Goal:** a live Firebase Hosting URL that reaches FastAPI on Cloud Run, with anonymous sign-in working. Skill: `deploy-check`, then `phase-check`.

```
Read CLAUDE.md and REQUIREMENTS.md sections 9 to 11 and 14. Do Phase 1 only.
1. Create the repo structure from CLAUDE.md, with README.md stub, .gitignore, .env.example, requirements.txt, Dockerfile, MIT LICENSE, PROGRESS.md.
2. Backend: FastAPI with GET /health and a protected GET /api/whoami that verifies a Firebase ID token with firebase-admin and returns the user id; 401 on a missing or invalid token. config.py reads PROJECT_ID, REGION and model names from environment variables. Add the single JSON error shape from REQUIREMENTS.md section 10.
3. Frontend: a minimal frontend/index.html that signs in anonymously with Firebase Authentication and shows the result of /api/whoami.
4. firebase.json: Hosting public directory frontend, with a rewrite from /api/** to Cloud Run service "payproof" in [REGION], before any catch-all. Add Firestore security rules so a user can read and write only their own documents.
5. Tests: /health, and 401 on /api/whoami without a token.
6. Give me the exact deploy commands (gcloud run deploy, then firebase deploy --only hosting). Do not deploy without asking me.
Commit after each numbered item. Stop and summarise what to verify.
```

**You verify:** `pytest` passes; `/health` returns OK; the Hosting URL on a phone over mobile data shows a user id; `git tag phase-1`.
**Common issues:** 403 means the service is not public (`--allow-unauthenticated`); 404 on `/api/...` means the rewrite or the service name or region is wrong.

---

## Phase 2: Reading screenshots, plus the simulator (6 to 8 Oct, Tracks A and C in parallel)

**Goal:** an uploaded screenshot becomes validated JSON for three screen types, order offers are rejected, and the first accuracy table exists. Skills: `sim-data`, `eval-report`.

**Track A prompt (extraction):**

```
Read CLAUDE.md and REQUIREMENTS.md sections 3, 4.1 and 6. Do the Track A part of Phase 2 only.
1. Implement extraction/schema.py exactly as in section 4.1, extraction/prompt.py with all the rules in section 6 (including order_offer and other rejection, and no names, phone numbers or addresses), and extraction/extract.py. Check the current google-genai SDK documentation for Vertex AI usage and the current Gemini model names first, and tell me which models you chose. Structured JSON output, temperature 0, one retry, then needs_review=true.
2. POST /api/extract (multipart, Firebase token required): image processed in memory only, size and type limits, timeout handling, friendly errors. Never write the image anywhere or log it.
3. Per-user daily limits from REQUIREMENTS.md section 10 (config values), with a friendly over-limit message.
4. Tests for the schema (nulls, negatives, bad values), the prompt's rejection behaviour using mocked model output, and the limits. No network calls in tests.
Commit after each item. Stop and show me how to test /api/extract with one image.
```

**Track C prompt (simulator):**

```
Read CLAUDE.md and REQUIREMENTS.md sections 3, 4.1 and 12. Do Phase 2 for Track C only. Work only in eval/ and frontend/samples/.
1. eval/generate_data.py with Pillow: fictional platforms only; layouts L1, L2, L3 (positive) and N1, N2 (negative); English, [LANG_1], [LANG_2] with Noto fonts (tell me where you got them and their licence); noise: blur, tilt, crop, dark mode, JPEG compression, low brightness. Ground-truth JSON beside every image, validated against extraction/schema.py. Include variants that omit distance or minutes. A fixed seed. A deny list of real platform names checked before writing any file.
2. Generate 30 images first, then show me 6 so I can judge realism.
3. eval/run_extraction_eval.py: field-level accuracy by screen type, language, layout and noise, plus the rejection rate for N1 and N2. Print a table and write eval/RESULTS.md.
4. Create docs/SIMULATION.md describing what is simulated and how.
Commit after each item.
```

**You verify:** open 5 generated images (they must look like real app screens in invented brands); `/api/extract` returns JSON for a trip, a weekly screen, and rejects an order offer; the first accuracy table exists. **Gate 8 Oct.** `git tag phase-2`.

---

## Phase 3: Pay engine, weekly mode, storage (8 to 9 Oct, Track A; histories by Track C)

**Goal:** exact, tested formulas for both modes; every number the app shows comes from here. Skills: `grounding-audit` (later), `phase-check`.

```
Read CLAUDE.md and REQUIREMENTS.md sections 4.2, 5 and 10. Do Phase 3 only. No LLM or network call anywhere in engine/.
1. engine/models.py and engine/earnings.py: trip mode and weekly mode with the exact definitions in sections 5.1 and 5.2. Return None, never zero, for zero denominators or missing data; include data_quality notes; reject negative inputs.
2. tests/test_engine.py: first both worked examples from the document (trip: 128, 192.00, 85.33, 20.00, 0.0588; weekly: 6,120, 127.50, 15.77, 0.0353), then at least 8 more hand-computed cases for each mode (nulls, zero distance, zero minutes, reconciliation gap, several deductions, a single trip, negative input, a large list, weekly with total_credited missing). Show the hand calculation for each in a comment.
3. engine/changes.py (trip mode: seeded bootstrap, 15-trip minimum, 5% threshold) and engine/weekly.py (3 earlier weeks plus the latest, 10% threshold, simple comparison). Tests for every status.
4. Firestore store in backend/store.py under users/{uid}/..., and the endpoints PUT /api/trips, PUT /api/weeks, PUT /api/costs, GET /api/summary, GET /api/changes. The user id comes only from the verified token.
5. DELETE /api/data that removes everything for the user.
Commit after each item. Stop and show me the test output.
```

**Track C in parallel:** extend the generator to produce the 40 simulated trip histories and 40 weekly histories (REQUIREMENTS.md section 12).
**You verify:** `pytest -v` passes; read the hand calculations for 3 cases yourself; another user's data is rejected; `git tag phase-3`.

---

## Phase 4: Grounded answers, evidence pack, optional Listen (9 to 11 Oct, Track A; evals by Track C)

**Goal:** Gemini explains in the worker's language and no unsupported number gets through. Skills: `grounding-audit`, `eval-report`, `phase-check`.

```
Read CLAUDE.md and REQUIREMENTS.md sections 7, 8 and 10. Do Phase 4 only.
1. backend/qa.py: Gemini function calling with get_summary, get_changes, get_trip_stats and get_weekly returning engine results. The model may state only numbers those tools returned. Languages: English, [LANG_1], [LANG_2] through a language parameter.
2. The number verifier exactly as in section 7.2 (including Indian digit grouping and Hindi and Tamil numerals), with one retry then a refusal naming what is missing. Unit tests with passing, failing and edge cases, no network calls.
3. Refusals per section 7.3.
4. POST /api/ask returns a verified answer with an answer_id and stores it under users/{uid}/answers.
5. GET /api/report returns the self-contained HTML evidence pack described in section 8.
6. Global and per-user usage limits for questions.
Commit after each item. Stop and show me one answerable and one unanswerable question working.
```

**Optional (decide 11 Oct, only if the core is done):** the "Listen" button per REQUIREMENTS.md section 7.4. Paste this separately:

```
Read REQUIREMENTS.md section 7.4. Add POST /api/tts that takes an answer_id of a stored verified answer, never free text, and returns audio using Gemini text to speech for [LANG_1] and [LANG_2]. Check the current Text-to-Speech documentation for model names, languages and regional support, and tell me what you chose. Add a Listen button in the UI. Tests with mocked audio. Do not touch any other feature.
```

**Track C in parallel:** `eval/run_change_eval.py` and `eval/run_grounding_eval.py`; append both tables to `eval/RESULTS.md`.
**You verify:** an unanswerable question is refused; a native speaker reads the `[LANG_1]` and `[LANG_2]` answers; the report says "possible change", never "cheating"; `git tag phase-4`.

---

## Track B: Front end (6 to 12 Oct, runs in parallel)

**Start on 6 Oct against mock data**, then wire to the real API from 11 Oct. Skill: `phase-check`, `grounding-audit`.

```
Read CLAUDE.md and REQUIREMENTS.md sections 4, 9 and 10. You are Track B: work only in frontend/. Plain HTML, CSS and vanilla JavaScript, mobile-first, minimal, no build step, system fonts, Firebase web SDK only.
1. Create frontend/mock/ with JSON responses that match REQUIREMENTS.md sections 4 and 10 for: a trip extraction, a weekly extraction, a rejected order offer, a summary, a weekly summary, a possible-change result, an insufficient-data result, a verified answer and a refusal.
2. Build every screen in FE-1 to FE-14 against the mocks, behind one small api.js module so switching to the real API changes one file.
3. Sample mode (FE-2): load images from frontend/samples/ (use placeholders until Track C delivers them).
4. UI labels in English, [LANG_1] and [LANG_2].
Commit per screen. Stop and tell me how to test on my phone.
```

**From 11 Oct (integration):** switch `api.js` to the real endpoints, send the Firebase ID token, handle every error and loading state, and test the whole flow on a phone.

---

## Phase 5: Integration and privacy (11 to 12 Oct, Tracks A and B)

- [ ] Run acceptance scenarios A1 to A12 from REQUIREMENTS.md section 16; list what fails
- [ ] Run the whole flow on a phone over mobile data using the sample button, in a private window
- [ ] Privacy test: delete data, then confirm Firestore is empty; confirm no image is stored (check Cloud Storage and logs)
- [ ] Run `grounding-audit`: every number the UI shows must come from the API
- [ ] Confirm all four teammates still see the team on the portal
- [ ] `git tag phase-5`

---

## Phase 6: Evaluation and hardening (12 to 14 Oct)

**Goal:** real numbers in `eval/RESULTS.md` and a demo that never fails. Skills: `eval-report`, `demo-rehearsal`, `deploy-check`.

```
Read CLAUDE.md and REQUIREMENTS.md sections 12, 13 and 16. Do Phase 6 only.
1. Scale the simulated set to 60-80 labelled screenshots; run all evaluation scripts, including a latency script on the deployed app; update eval/RESULTS.md with real numbers, failure types and honest notes on weak spots.
2. Fix the top 3 failure types without special-casing the test images.
3. Friendly handling for: oversized image, unreadable image, non-earnings image, network failure, Gemini timeout, over-limit.
4. Write docs/DEMO.md with the exact demo steps and timings for a video of 2:55 to 3:00.
5. Structured logging without images or personal data.
Commit after each item. Tag v1.0 when finished. Stop and show me RESULTS.md.
```

**You verify:** run the demo path 3 times in a row with no failures; set Cloud Run minimum instances to 1; add a Cloud Monitoring uptime check on `/health`; check the billing alert and remaining credits; **`git tag v1.0` on 14 Oct (feature freeze)**.

---

## Phase 7: Docs, deck, video and form (14 to 16 Oct, Track D leads)

```
Do Phase 7 only. No new features.
1. README.md: problem, solution, architecture (how Firebase Hosting, Firebase Authentication, Firestore, Cloud Run and Gemini are used), how to run locally, evaluation results copied from eval/RESULTS.md, limits, privacy.
2. docs/ARCHITECTURE.md with a Mermaid diagram.
3. docs/submission_description.md: at most 1,024 characters, naming Firebase, Firestore, Cloud Run and Gemini, with the real evaluation numbers. Show me the character count.
4. A final secrets scan of the repo and git history; report anything suspicious.
Commit after each item.
```

**Track D does (not Claude Code):**
- [ ] Fill the deck (official template) slides 9, 10, 11 and 13 with the real cost, screenshots, results and links; export to PDF under 5 MB
- [ ] Record the video on the deployed URL: 2:55 to 3:00 (the form says up to 3 minutes, the rules text says 3 to 4; ask Hack2skill); it must clearly show the working functionality; upload as unlisted; open the link in a private window
- [ ] Choose the challenge track after reading both descriptions
- [ ] Test every link in a private window on a phone

Skill: `submission-check`.

---

## 17 Oct: Submit

- [ ] The prototype link (Firebase Hosting URL) works in a private window on mobile data, and the sample button completes the flow
- [ ] Repo public, README renders, no secrets
- [ ] Deck PDF under 5 MB, official template
- [ ] Video link opens and is at most 3 minutes
- [ ] Description at most 1,024 characters, names all four Google services
- [ ] Submit; screenshot the confirmation

**After submitting:** the roadmap shows prototype evaluation from 19 Oct to 6 Nov and the Top 50 announcement on 7 Nov. Keep the app running, check it daily, and do not redeploy risky changes. There are no retries if it is down during evaluation.

---

## Cut list (cut in this order if you fall behind)

1. The optional Listen (text to speech) feature
2. A third language (keep English plus one)
3. Pay-change signal for weekly mode (keep trip mode, or the reverse if weekly data is what workers actually have)
4. PDF export of the evidence pack (HTML is enough)
5. UI polish (UX is only 10% of the score)
6. **Never cut:** engine tests, the number verifier, the sample button, the evaluation tables, the live link

## Daily rhythm

- 15-minute check-in: done, blocked, next
- Each person commits at least once a day and runs `phase-check` before merging
- Update `PROGRESS.md` at the end of each phase
- Check the billing dashboard and the live app every day
