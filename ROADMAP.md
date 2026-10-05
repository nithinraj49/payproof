# PayProof: solo build roadmap for Claude Code (v3, from 5 Oct 2026)

> One person (Nithin) builds everything, alongside a day job. Put this next to `CLAUDE.md` and `REQUIREMENTS.md` in the repo root.
> `REQUIREMENTS.md` says WHAT to build. **Where this file's "Solo overrides" conflict with it, this file wins.**
> The form closes Sun 18 Oct, 11:59 PM IST. We submit on **Sat 17 Oct**. Today is Mon 5 Oct.
> Placeholders: `[PROJECT_ID]`, `[REGION]`, `[LANG_1]` (default Hindi), `[LANG_2]` (only if time allows).

## Strategy: build the floor first, then widen

With about 49 working hours in total, the order matters more than the polish. Build a thin version that works end to end, deploy it, then widen. If the floor works, we can always submit.

### The floor: minimum viable demo (must work before anything else is widened)

1. A new visitor opens the live link in a private window and taps **Try with sample screenshots**. No sign-up.
2. A trip screenshot and a weekly payout screenshot are read into a table; an order-offer screenshot is rejected with a reason.
3. The user confirms (a read-only table is acceptable at first), enters costs, and sees net earnings, **both hourly rates** (trip mode), pay per km and deduction share.
4. One grounded question is answered in English and `[LANG_1]` with a "verified" label; an unanswerable question is refused.
5. The evidence pack opens; **Delete all my data** works.
6. All of it runs on Firebase Hosting, Cloud Run, Firestore and Gemini.

### Solo overrides (these win over REQUIREMENTS.md)

| Area | Solo rule |
|---|---|
| Languages | English plus `[LANG_1]` only. Add `[LANG_2]` only if the 8 Oct gate passes with time to spare |
| Simulator | Start with layouts L1, L3 and N1. Add L2 and N2 only if time allows |
| Weekly mode | Extraction, engine and results: yes. Weekly pay-change detection: **not built** |
| Trip mode | Everything, including the bootstrap pay-change signal |
| Evaluation set | 40 simulated screenshots and 20 histories (not 60 to 80 and 40) |
| Listen (text to speech) | Not built, unless everything else is done by 14 Oct (unlikely) |
| Usage limits | One simple per-user daily limit and one global cap |
| Evidence pack | Plain HTML only |
| Acceptance scenarios | A1 to A10 must pass; A11 and A12 if time allows |
| Never cut | The live link, the sample button, the number verifier, privacy and delete, the evaluation tables |

## Schedule (assumes about 3 hours on weekdays and 8 on the weekend; change it if your real hours differ)

| Day | Date | Hours | Work |
|---|---|---|---|
| 1 | Mon 5 Oct | 3 | Phase 0 setup; start Phase 1 |
| 2 | Tue 6 Oct | 3 | Finish Phase 1: **live URL**, sign-in works |
| 3 | Wed 7 Oct | 3 | Phase 2: simulator-lite, extraction |
| 4 | Thu 8 Oct | 3 | Phase 2: first accuracy table; **gate** |
| 5 | Fri 9 Oct | 3 | Phase 3: engine and tests |
| 6 | Sat 10 Oct | 8 | Phase 3: change signal, storage, endpoints; Phase 4: Q&A, verifier, evidence pack |
| 7 | Sun 11 Oct | 8 | Phase 5: the front end, sample mode, integration; **floor works** |
| 8 | Mon 12 Oct | 3 | Phase 6: acceptance scenarios, privacy test, grounding audit |
| 9 | Tue 13 Oct | 3 | Phase 6: evaluation run, fixes |
| 10 | Wed 14 Oct | 3 | Hardening; three clean demo runs; **tag v1.0 (feature freeze)** |
| 11 | Thu 15 Oct | 3 | Phase 7: docs, description, deck |
| 12 | Fri 16 Oct | 3 | Video, form drafted, final checks |
| 13 | Sat 17 Oct | 4 | Buffer, then **submit** |
| 14 | Sun 18 Oct | 0 | Emergency only |

After submitting: keep the app live and check it daily (15 minutes) through the evaluation period, 19 Oct to 6 Nov, and until the Top 50 announcement on 7 Nov.

### Checkpoints that force a decision

| When | Question | If the answer is no |
|---|---|---|
| **Thu 8 Oct evening** | Is field accuracy acceptable on 20+ simulated images? (suggested bar: 80%) | Drop to English only and two layouts; keep going |
| Sat 10 Oct night | Do the engine, storage and Q&A all work through the API? | Cut the evidence pack to a plain summary |
| **Sun 11 Oct night** | Does the floor work end to end? | Stop widening. Spend Monday only on the floor |
| **Wed 14 Oct** | Three clean demo runs? | Fix, not features. Tag `v1.0` anyway |

## How to work with Claude Code

1. Open the terminal in `C:\dev\payproof` and run `claude`.
2. Paste ONE prompt at a time. Review, run `pytest`, use the `phase-check` skill, then commit and tag.
3. Say no to anything outside `REQUIREMENTS.md` (new libraries, new services) unless the phase needs it.
4. Keep sessions focused: one phase per session; start a fresh session for the next phase, since `CLAUDE.md` reloads automatically.
5. When Claude Code writes code that calls Gemini, Firebase or Vertex AI, make it check the current documentation and tell you which model names it chose.

---

## Phase 0: Setup (Mon 5 Oct, about 1.5 hours, you)

- [ ] Already done: Python, Git, Node.js, npm, `gcloud`, Claude Code, the public repo with specs and skills
- [ ] `npm install -g firebase-tools`, then `firebase --version`
- [ ] `gcloud auth login`, `gcloud auth application-default login`, `firebase login`
- [ ] Create Google Cloud project `[PROJECT_ID]`; link billing; claim the hackathon credits (see your portal's Resources or Announcements); set a **billing budget alert**
- [ ] `gcloud config set project [PROJECT_ID]`
- [ ] `gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com firestore.googleapis.com firebase.googleapis.com identitytoolkit.googleapis.com`
- [ ] Firebase console: add Firebase to the SAME project; enable Authentication (Anonymous and Google); create Firestore in native mode (suggested `asia-south1`; the location cannot be changed later)
- [ ] Gemini models on Vertex AI may not exist in every region. Plan a separate `VERTEX_LOCATION` setting, and tell Claude Code about it in Phase 2

---

## Phase 1: Skeleton and first deploy (Mon 5 to Tue 6 Oct)

**Goal:** a live Firebase Hosting URL that reaches FastAPI on Cloud Run, with anonymous sign-in working. Skills: `deploy-check`, `phase-check`.

```
Read CLAUDE.md, ROADMAP.md (Solo overrides) and REQUIREMENTS.md sections 9 to 11 and 14. Do Phase 1 only. A LICENSE file already exists; do not recreate or change it.
1. Create the repo structure from CLAUDE.md and REQUIREMENTS.md: README.md stub, .gitignore (include .env and any service-account JSON), .env.example, requirements.txt, Dockerfile, PROGRESS.md.
2. Backend: FastAPI with GET /health and a protected GET /api/whoami that verifies a Firebase ID token with firebase-admin and returns the user id; 401 on a missing or invalid token. config.py reads PROJECT_ID, REGION, VERTEX_LOCATION and model names from environment variables. Use the single JSON error shape from REQUIREMENTS.md section 10.
3. Frontend: a minimal frontend/index.html that signs in anonymously with Firebase Authentication and shows the result of /api/whoami.
4. firebase.json: Hosting public directory frontend, with a rewrite from /api/** to Cloud Run service "payproof" in [REGION], before any catch-all. Add Firestore security rules so a user can read and write only their own documents.
5. Tests: /health, and 401 on /api/whoami without a token.
6. Give me the exact deploy commands (gcloud run deploy, then firebase deploy --only hosting). Do not deploy without asking me.
Commit after each numbered item. Stop and summarise what to verify.
```

**You verify:** `pytest` passes; `/health` returns OK; the Hosting URL on your phone over mobile data shows a user id; `git tag phase-1 && git push --tags`.
**Common issues:** 403 from Cloud Run means the service is not public (`--allow-unauthenticated`); 404 on `/api/...` means the rewrite, service name or region is wrong.

---

## Phase 2: Simulator-lite and reading screenshots (Wed 7 to Thu 8 Oct)

**Goal:** an uploaded screenshot becomes validated JSON for trip and weekly screens, order offers are rejected, and the first accuracy table exists. Skills: `sim-data`, `eval-report`, `phase-check`.

**Step A: simulator-lite (about 1 hour)**

```
Read CLAUDE.md and REQUIREMENTS.md sections 3, 4.1 and 12, and ROADMAP.md Solo overrides. Do step A of Phase 2 only.
1. eval/generate_data.py with Pillow: FICTIONAL platforms only; layouts L1 (trip detail), L3 (weekly payout) and N1 (order offer), in English and [LANG_1] with Noto fonts (tell me where you got them and their licence). Noise: blur, tilt, crop, dark mode, JPEG compression. Include variants that omit distance or minutes. Ground-truth JSON beside every image, validated against extraction/schema.py. Fixed seed. A deny list of real platform names checked before writing any file. Never copy a real platform's design.
2. Generate 30 images and show me 6 so I can judge realism.
Commit after each item.
```

**Step B: extraction (about 2 hours)**

```
Read CLAUDE.md and REQUIREMENTS.md sections 3, 4.1 and 6. Do step B of Phase 2 only.
1. extraction/schema.py exactly as in section 4.1, extraction/prompt.py with all the rules in section 6 (including rejecting order_offer and other screens, and never extracting names, phone numbers or addresses), and extraction/extract.py. Check the current google-genai SDK documentation for Vertex AI usage and the current Gemini model names first, and tell me which models you chose. Structured JSON output, temperature 0, one retry, then needs_review=true.
2. POST /api/extract (multipart, Firebase token required): image processed in memory only, size and type limits, timeout handling, friendly errors. Never write the image anywhere or log it.
3. One simple per-user daily limit and one global cap, with a friendly over-limit message.
4. eval/run_extraction_eval.py: field-level accuracy by screen type, language, layout and noise, plus the rejection rate for N1. Print a table and write eval/RESULTS.md.
5. Tests for the schema and the rejection behaviour using mocked model output. No network calls in tests.
Commit after each item. Stop and show me the accuracy table.
```

**You verify:** open 5 generated images (they must look like real app screens in invented brands); `/api/extract` returns JSON for a trip, a weekly screen, and rejects an offer; the accuracy table exists. **Gate Thu 8 Oct.** `git tag phase-2`.

---

## Phase 3: Pay engine (Fri 9 Oct, then Sat 10 Oct morning)

**Goal:** exact, tested formulas for trip and weekly modes; every number the app shows comes from here. No LLM call in `engine/`. Skill: `phase-check`.

```
Read CLAUDE.md and REQUIREMENTS.md sections 4.2, 5 and 10, and ROADMAP.md Solo overrides. Do Phase 3 only. No LLM or network call anywhere in engine/.
1. engine/models.py and engine/earnings.py: trip mode and weekly mode with the exact definitions in sections 5.1 and 5.2. Return None, never zero, for zero denominators or missing data; include data_quality notes; reject negative inputs.
2. tests/test_engine.py: first both worked examples from the document (trip: 128, 192.00, 85.33, 20.00, 0.0588; weekly: 6,120, 127.50, 15.77, 0.0353), then at least 8 more hand-computed cases for each mode (nulls, zero distance, zero minutes, reconciliation gap, several deductions, a single trip, negative input, a large list, weekly with total_credited missing). Show the hand calculation for each in a comment.
3. engine/changes.py for trip mode only: seeded bootstrap with 10,000 resamples, 15-trip minimum, 5% threshold, statuses possible_change, no_clear_change, insufficient_data. Tests for every status. Do not build weekly change detection.
4. backend/store.py (Firestore under users/{uid}/...) and the endpoints PUT /api/trips, PUT /api/weeks, PUT /api/costs, GET /api/summary, GET /api/changes, DELETE /api/data. The user id comes only from the verified token.
5. Extend eval/generate_data.py to produce 20 simulated trip histories (half with an injected 10% per-km pay cut) and eval/run_change_eval.py for precision, recall and false alarms.
Commit after each item. Stop and show me the test output.
```

**You verify:** `pytest -v` passes; read the hand calculations for three cases yourself; another user's data is rejected; `git tag phase-3`.

---

## Phase 4: Grounded answers and evidence pack (Sat 10 Oct)

**Goal:** Gemini explains in the worker's language and no unsupported number gets through. Skills: `grounding-audit`, `phase-check`.

```
Read CLAUDE.md and REQUIREMENTS.md sections 7, 8 and 10, and ROADMAP.md Solo overrides. Do Phase 4 only.
1. backend/qa.py: Gemini function calling with get_summary, get_changes, get_trip_stats and get_weekly returning engine results. The model may state only numbers those tools returned. Languages: English and [LANG_1] through a language parameter.
2. The number verifier exactly as in section 7.2 (including Indian digit grouping and Devanagari or Tamil numerals as relevant to [LANG_1]), one retry then a refusal that names what is missing. Unit tests with passing, failing and edge cases; no network calls.
3. Refusals per section 7.3.
4. POST /api/ask returns a verified answer with an answer_id and stores it under users/{uid}/answers.
5. GET /api/report returns a plain self-contained HTML evidence pack as in section 8.
6. eval/run_grounding_eval.py with 20 questions including unanswerable ones; append its table to eval/RESULTS.md.
Commit after each item. Stop and show me one answerable and one unanswerable question working.
```

**You verify:** an unanswerable question is refused; someone who reads `[LANG_1]` checks the answers; the report says "possible change", never "cheating"; `git tag phase-4`.

---

## Phase 5: Front end and sample mode (Sun 11 Oct, about 8 hours)

**Goal:** the floor works end to end. The clickable prototype is the design reference. Skill: `grounding-audit`.

**Step A: screens (about 5 hours)**

```
Read CLAUDE.md and REQUIREMENTS.md sections 4, 9 and 10, and ROADMAP.md Solo overrides. Do step A of Phase 5 only. Work in frontend/. Plain HTML, CSS and vanilla JavaScript, mobile-first, minimal, no build step, system fonts, the Firebase web SDK only.
1. One small api.js module that sends the Firebase ID token and handles every error and loading state in one place.
2. Screens FE-1 to FE-12 from the document, using the real API: first screen with "Try with sample screenshots" and "Upload my screenshots"; table matching the screen type with yellow low-confidence cells; rejected screens with a clear reason; km and hours inputs for weekly mode; costs; results with BOTH hourly rates and a one-line explanation; changes; ask with a language selector and a verified label; evidence pack; delete.
3. UI labels in English and [LANG_1].
Commit per screen. Stop and tell me how to test on my phone.
```

**Step B: sample mode (about 1.5 hours)**

```
Read REQUIREMENTS.md FE-2. Add sample mode: curate about 6 simulated images (a trip screen, a weekly screen, one order offer) into frontend/samples/ with a small index file, and make the "Try with sample screenshots" button run the REAL flow end to end with them. A visitor must complete it in a private window with no sign-up. Commit.
```

**You verify:** the floor, step by step, in a private window on your phone over mobile data; `git tag phase-5`. **Checkpoint Sun 11 Oct night.**

---

## Phase 6: Test and harden (Mon 12 to Wed 14 Oct)

**Goal:** real numbers in `eval/RESULTS.md` and a demo that never fails. Skills: `eval-report`, `demo-rehearsal`, `deploy-check`, `grounding-audit`.

**Mon 12 Oct.** Run acceptance scenarios A1 to A10 from `REQUIREMENTS.md` section 16 and list what fails. Privacy test: delete data, confirm Firestore is empty; confirm no image is stored (check logs and Cloud Storage). Run `grounding-audit`.

**Tue 13 Oct (paste into Claude Code):**

```
Read CLAUDE.md and REQUIREMENTS.md sections 12, 13 and 16, and ROADMAP.md Solo overrides. Do this part of Phase 6 only.
1. Scale the simulated set to 40 labelled screenshots and 20 histories; run all evaluation scripts, including a latency script against the deployed app (ask me for the URL); update eval/RESULTS.md with real numbers, failure types and honest notes on weak spots.
2. Fix the top 3 failure types without special-casing the test images.
3. Friendly handling for: oversized image, unreadable image, non-earnings image, network failure, Gemini timeout, over-limit.
Commit after each item. Stop and show me RESULTS.md.
```

**Wed 14 Oct (paste into Claude Code):**

```
Do the last part of Phase 6. Write docs/DEMO.md with the exact demo steps and timings for a video of 2:55 to 3:00 using only sample data. Add structured logging without images or personal data. Then stop.
```

**You do:** run the demo path three times in a row with no failures; set Cloud Run minimum instances to 1; add a Cloud Monitoring uptime check on `/health`; check the billing alert and remaining credits; **`git tag v1.0` on 14 Oct (feature freeze)**.

---

## Phase 7: Docs, deck, video, form (Thu 15 to Fri 16 Oct)

**Thu 15 Oct (paste into Claude Code):**

```
Do Phase 7 only. No new features.
1. README.md: problem, solution, architecture (how Firebase Hosting, Firebase Authentication, Firestore, Cloud Run and Gemini are used), how to run locally, evaluation results copied from eval/RESULTS.md, limits, privacy.
2. docs/ARCHITECTURE.md with a Mermaid diagram.
3. docs/submission_description.md: at most 1,024 characters, naming Firebase, Firestore, Cloud Run and Gemini, with the real evaluation numbers. Show me the character count.
4. A final secrets scan of the repo and git history; report anything suspicious.
Commit after each item.
```

**You do:**
- [ ] Fill deck slides 9, 10, 11 and 13 with real cost, screenshots, results and links; export to PDF under 5 MB
- [ ] Choose the challenge track after reading both descriptions (Sustainability and Social Impact, or Future of Work and Enterprise Productivity)
- [ ] **Fri 16 Oct:** record the video on the deployed URL, 2:55 to 3:00, sample data only; upload as unlisted; open the link in a private window
- [ ] Run `submission-check`; draft all six form items

---

## Sat 17 Oct: Submit

- [ ] The prototype link (Firebase Hosting URL) works in a private window on mobile data, and the sample button completes the flow
- [ ] Repo public, README renders, no secrets
- [ ] Deck PDF under 5 MB, official template
- [ ] Video link opens and is at most 3 minutes
- [ ] Description at most 1,024 characters, names Firebase, Firestore, Cloud Run and Gemini
- [ ] Submit and screenshot the confirmation

**After submitting:** do not redeploy risky changes. There are no retries if the app is down during evaluation.

---

## If you fall behind, cut in this order

1. `[LANG_2]` (already cut) and the Listen feature (already cut)
2. Editing of table rows (a read-only confirm table is acceptable)
3. Weekly mode UI polish (keep the numbers)
4. The evidence pack styling
5. UI polish generally (UX is 10% of the score)
6. Evaluation set size (keep at least 20 images, and say so honestly)
7. **Never cut:** the live link, the sample button, the number verifier, privacy and delete, the evaluation tables

## Daily rhythm

- 10-minute plan at the start of each session: which prompt, what "done" looks like
- Commit at least once a day; run `phase-check` before tagging
- Update `PROGRESS.md` at the end of each session
- Check the billing dashboard and the live app every day from 14 Oct onward
