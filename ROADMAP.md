# PayProof: solo build roadmap for Claude Code (v4, from 6 Oct 2026)

> One person (Nithin) builds everything, alongside a day job. Put this next to `CLAUDE.md` and `REQUIREMENTS.md` in the repo root.
> `REQUIREMENTS.md` says WHAT to build (read section 0 for project facts, section 19 for cost controls, section 20 for environment variables). **Where this file's "Solo overrides" conflict with it, this file wins.**
> The form closes Sun 18 Oct, 11:59 PM IST. We submit on **Sat 17 Oct**. Today is Tue 6 Oct.
> This roadmap covers the PROTOTYPE (Phases 1 to 6). The demo video, deck and submission documents (Phase 7) come after the prototype works and are done separately.

## Strategy: build the floor first, then widen

With about 45 working hours left, the order matters more than the polish. Build a thin version that works end to end, deploy it, then widen. If the floor works, we can always submit.

### The floor: minimum viable demo (must work before anything else is widened)

1. A new visitor opens the live link in a private window and taps **Try with sample screenshots**. No sign-up.
2. A trip screenshot and a weekly payout screenshot are read into a table; an order-offer screenshot is rejected with a reason.
3. The user confirms (a read-only table is acceptable at first), enters costs, and sees net earnings, **both hourly rates** (trip mode), pay per km and deduction share.
4. One grounded question is answered in English with a "verified" label; an unanswerable question is refused.
5. The evidence pack opens; **Delete all my data** works.
6. All of it runs on Firebase Hosting, Cloud Run, Firestore and Gemini (Vertex AI when deployed).

### Solo overrides (these win over REQUIREMENTS.md)

| Area | Solo rule |
|---|---|
| Languages | **English only for now.** A regional language is a stretch goal (see "Stretch" below), decided after the floor works, and only if you can check every string |
| Simulator | Start with layouts L1, L3 and N1. Add L2 and N2 only if time allows |
| Weekly mode | Extraction, engine and results: yes. Weekly pay-change detection: **not built** |
| Trip mode | Everything, including the bootstrap pay-change signal |
| Evaluation set | 40 simulated screenshots and 20 histories (not 60 to 80 and 40) |
| Listen (text to speech) | Not built |
| Usage limits | Defaults in REQUIREMENTS.md section 10 (12 extractions and 25 questions per user per day, global cap 400 Gemini calls per day) |
| Evidence pack | Plain HTML only |
| Acceptance scenarios | A1 to A10 and A13 must pass; A11 and A12 if time allows |
| Never cut | The live link, the sample button, the number verifier, privacy and delete, the evaluation tables, the cost limits |

## Setup status (done)

- [x] Python, Git, Node, npm, `gcloud`, `firebase`, Claude Code installed; public repo with specs and skills
- [x] Google Cloud project `payproof-nithin-2026` with billing linked; services enabled
- [x] Firebase added to the project; Firestore created (native mode, Standard, `asia-south1`)
- [ ] Authentication: Anonymous and Google enabled (check in the Firebase console)
- [ ] Billing budget alert created (do this before the first deploy)
- [ ] If the billing account is a free trial: write down its expiry date and upgrade before it, or the app stops
- [ ] Hack2skill confirmed: no credits are provided, the video limit is up to 3 minutes

## Schedule (about 3 hours on weekdays and 8 on the weekend; change it if your real hours differ)

| Day | Date | Hours | Work |
|---|---|---|---|
| 2 | Tue 6 Oct | 3 | Phase 1: skeleton, local tests; deploy once billing and Auth are confirmed |
| 3 | Wed 7 Oct | 3 | Phase 2: simulator-lite, extraction |
| 4 | Thu 8 Oct | 3 | Phase 2: first accuracy table; **gate** |
| 5 | Fri 9 Oct | 3 | Phase 3: engine and tests |
| 6 | Sat 10 Oct | 8 | Phase 3: change signal, storage, endpoints; Phase 4: Q&A, verifier, evidence pack |
| 7 | Sun 11 Oct | 8 | Phase 5: the front end, sample mode, integration; **floor works** |
| 8 | Mon 12 Oct | 3 | Phase 6: acceptance scenarios, privacy test, grounding audit |
| 9 | Tue 13 Oct | 3 | Phase 6: evaluation run (cost gate first), fixes |
| 10 | Wed 14 Oct | 3 | Hardening; three clean demo runs; cold-start decision; **tag v1.0 (feature freeze)** |
| 11 to 13 | 15 to 17 Oct | 10 | Phase 7 (separate): docs, deck, video, form; **submit on Sat 17 Oct** |

After submitting: keep the app live and check it daily (15 minutes) through the evaluation period, 19 Oct to 6 Nov, and until the Top 50 announcement on 7 Nov.

### Checkpoints that force a decision

| When | Question | If the answer is no |
|---|---|---|
| **Thu 8 Oct evening** | Is field accuracy acceptable on 20+ simulated images? (suggested bar: 80%) | Drop to English only and two layouts; keep going |
| Sat 10 Oct night | Do the engine, storage and Q&A all work through the API? | Cut the evidence pack to a plain summary |
| **Sun 11 Oct night** | Does the floor work end to end? | Stop widening. Spend Monday only on the floor |
| **Wed 14 Oct** | Three clean demo runs? Cold-start time acceptable? | Fix, not features. Tag `v1.0` anyway |

## How to work with Claude Code

1. Use the VS Code Claude Code panel (or the terminal) in `C:\dev\payproof`. Keep permission mode on **Manual**.
2. One phase per session, or one master-prompt session that works through Phases 1 to 6 and stops at checkpoints. At the end of each phase: `pytest`, the `phase-check` skill, update `PROGRESS.md`, commit.
3. Say no to anything outside `REQUIREMENTS.md` (new libraries, new services) unless the phase needs it.
4. When Claude Code writes code that calls Gemini, Firebase or Vertex AI, it must check the current documentation and tell you which model names and prices it found.

### Where Claude Code must stop and ask you

1. Before any deploy command and any `git push`: show the exact command and wait.
2. When it needs a secret: it tells you which `.env` entries to fill. You never paste secrets in chat, and it never prints or commits `.env`.
3. Before any bulk Gemini run (evaluation, batch tests): the number of calls and the estimated cost, then wait for your "go".
4. After the first extraction accuracy table.
5. Before a dependency or a change to the spec, and before any task that would cost more than about an hour and is not on the floor.
6. Before adding any non-English feature (none for now).

### AI cost rules (we pay for every Gemini call; full list in REQUIREMENTS.md section 19)

One Gemini call per screenshot (one retry at most); resize images to at most 1280 px and JPEG quality 85 before sending; cap output tokens; compact JSON for Q&A with at most two calls per question; cache sample-image results; in-app usage limits with Firestore counters; log token counts; mocked Gemini in tests; Cloud Run `--max-instances=3`.

---

## Phase 1: Skeleton and first deploy (Tue 6 Oct)

**Goal:** a live Firebase Hosting URL that reaches FastAPI on Cloud Run, with anonymous sign-in working. Skills: `deploy-check`, `phase-check`.

```
Read CLAUDE.md, ROADMAP.md (Solo overrides) and REQUIREMENTS.md sections 0, 9 to 11, 14, 19 and 20. Do Phase 1 only. A LICENSE file already exists; do not recreate or change it.
1. Create the repo structure from CLAUDE.md and REQUIREMENTS.md: README.md stub, .gitignore (include .env, firebase-debug.log and any service-account JSON; keep existing entries), .env.example with every variable in section 20, requirements.txt, Dockerfile, PROGRESS.md.
2. Backend: FastAPI with GET /health and a protected GET /api/whoami that verifies a Firebase ID token with firebase-admin and returns the user id; 401 on a missing or invalid token. config.py reads every variable in section 20 from the environment. One small Gemini client module that switches on GEMINI_BACKEND (aistudio or vertex); do not call Gemini yet. Use the single JSON error shape from section 10.
3. Frontend: a minimal frontend/index.html that signs in anonymously with Firebase Authentication and shows the result of /api/whoami. Put the Firebase web config in frontend/firebase-config.js (tell me where to copy the values from).
4. firebase.json: Hosting public directory frontend, with a rewrite from /api/** to Cloud Run service "payproof", before any catch-all. First check the current Firebase documentation and tell me whether asia-south1 is supported for the rewrite; if not, propose a supported region. Add Firestore security rules so a user can read and write only their own documents.
5. Tests: /health, and 401 on /api/whoami without a token. No network calls in tests.
6. Give me the exact PowerShell deploy commands (gcloud run deploy with --max-instances=3, then firebase deploy --only hosting). Do not deploy until I approve.
Commit after each numbered item. Stop and summarise what I should verify.
```

**You verify:** `pytest` passes; `/health` returns OK; the Hosting URL on your phone over mobile data shows a user id; a budget alert exists; `git tag phase-1`.
**Common issues:** 403 from Cloud Run means the service is not public (`--allow-unauthenticated`); 404 on `/api/...` means the rewrite, service name or region is wrong; "not logged in" means run `firebase login` or `gcloud auth login` again.

---

## Phase 2: Simulator-lite and reading screenshots (Wed 7 to Thu 8 Oct)

**Goal:** an uploaded screenshot becomes validated JSON for trip and weekly screens, order offers are rejected, and the first accuracy table exists. Skills: `sim-data`, `eval-report`, `phase-check`.

**Step A: simulator-lite (about 1 hour)**

```
Read CLAUDE.md and REQUIREMENTS.md sections 3, 4.1 and 12, and ROADMAP.md Solo overrides. Do step A of Phase 2 only.
1. eval/generate_data.py with Pillow: FICTIONAL platforms only; layouts L1 (trip detail), L3 (weekly payout) and N1 (order offer), in English, with a free font (tell me where you got it and its licence). Noise: blur, tilt, crop, dark mode, JPEG compression. Include variants that omit distance or minutes. Ground-truth JSON beside every image, validated against extraction/schema.py. Fixed seed. A deny list of real platform names checked before writing any file. Never copy a real platform's design.
2. Generate 30 images and show me 6 so I can judge realism. No Gemini calls in this step.
Commit after each item.
```

**Step B: extraction (about 2 hours)**

```
Read CLAUDE.md and REQUIREMENTS.md sections 3, 4.1, 6, 10, 19 and 20. Do step B of Phase 2 only.
1. extraction/schema.py exactly as in section 4.1, extraction/prompt.py with all the rules in section 6 (including rejecting order_offer and other screens, and never extracting names, phone numbers or addresses), and extraction/extract.py. Check the current Gemini documentation and pricing first; tell me which model you chose for extraction, why it is the cheapest that should meet accuracy, and the approximate cost per call. Structured JSON output, temperature 0, capped output tokens, exactly one call per screenshot plus at most one retry, then needs_review=true.
2. Image preparation before sending: resize to at most IMAGE_MAX_SIDE_PX, JPEG at IMAGE_JPEG_QUALITY, strip metadata. In memory only.
3. POST /api/extract (multipart, Firebase token required): size and type limits, timeout handling, friendly errors. Never write the image anywhere or log it. Log token counts only.
4. Usage limits as atomic Firestore counters with the defaults in section 10, and a friendly over-limit message. Cache extraction results by image hash for the session.
5. eval/run_extraction_eval.py: field-level accuracy by screen type, layout and noise, plus the rejection rate for N1. It must print the number of Gemini calls and the estimated cost first and wait for my "go". Write eval/RESULTS.md.
6. Tests for the schema, the rejection behaviour, the limits and image preparation using mocked model output. No network calls in tests.
Commit after each item. Stop and show me the accuracy table and your recommendation.
```

**You verify:** open 5 generated images (they must look like real app screens in invented brands); `/api/extract` returns JSON for a trip, a weekly screen, and rejects an offer; the logs show one call per screenshot; the accuracy table exists. **Gate Thu 8 Oct.** `git tag phase-2`.

---

## Phase 3: Pay engine (Fri 9 Oct, then Sat 10 Oct morning)

**Goal:** exact, tested formulas for trip and weekly modes; every number the app shows comes from here. No LLM call in `engine/`. Skill: `phase-check`.

**Reminder (added 8 Oct 2026, from the Phase 1/2 deploy review):** when `engine/` is added, the Dockerfile must also get `COPY engine/ engine/`. A missing `COPY extraction/ extraction/` nearly shipped a broken container in Phase 2 — `backend/main.py` imported from `extraction/` but the Dockerfile only copied `backend/`, which would have crashed on startup with `ModuleNotFoundError`. Check every `backend/*.py` import against the Dockerfile's `COPY` list before every deploy, not just the first one.

```
Read CLAUDE.md and REQUIREMENTS.md sections 4.2, 5 and 10, and ROADMAP.md Solo overrides. Do Phase 3 only. No LLM or network call anywhere in engine/.
1. engine/models.py and engine/earnings.py: trip mode and weekly mode with the exact definitions in sections 5.1 and 5.2. Return None, never zero, for zero denominators or missing data; include data_quality notes; reject negative inputs.
2. tests/test_engine.py: first both worked examples from the document (trip: 128, 192.00, 85.33, 20.00, 0.0588; weekly: 6,120, 127.50, 15.77, 0.0353), then at least 8 more hand-computed cases for each mode (nulls, zero distance, zero minutes, reconciliation gap, several deductions, a single trip, negative input, a large list, weekly with total_credited missing). Show the hand calculation for each in a comment.
3. engine/changes.py for trip mode only: seeded bootstrap with 10,000 resamples, 15-trip minimum, 5% threshold, statuses possible_change, no_clear_change, insufficient_data. Tests for every status. Do not build weekly change detection.
4. backend/store.py (Firestore under users/{uid}/...) and the endpoints PUT /api/trips, PUT /api/weeks, PUT /api/costs, GET /api/summary, GET /api/changes, DELETE /api/data. The user id comes only from the verified token.
5. Extend eval/generate_data.py to produce 20 simulated trip histories (half with an injected 10% per-km pay cut) and eval/run_change_eval.py for precision, recall and false alarms (no Gemini calls needed).
Commit after each item. Stop and show me the test output.
```

**You verify:** `pytest -v` passes; read the hand calculations for three cases yourself; another user's data is rejected; `git tag phase-3`.

---

## Phase 4: Grounded answers and evidence pack (Sat 10 Oct)

**Goal:** Gemini explains the results in plain English and no unsupported number gets through. Skills: `grounding-audit`, `phase-check`.

```
Read CLAUDE.md and REQUIREMENTS.md sections 7, 8, 10 and 19, and ROADMAP.md Solo overrides. Do Phase 4 only.
1. backend/qa.py: Gemini function calling with get_summary, get_changes, get_trip_stats and get_weekly returning compact engine JSON. The model may state only numbers those tools returned. English only now; keep a `language` parameter (default `en`) in the API so a language can be added later. Use the cheapest suitable model, capped output, at most two model calls per question.
2. The number verifier exactly as in section 7.2 (including Indian digit grouping such as 1,23,456), one retry then a refusal that names what is missing. Unit tests with passing, failing and edge cases; mocked model output, no network calls.
3. Refusals per section 7.3.
4. POST /api/ask returns a verified answer with an answer_id and stores it under users/{uid}/answers. Apply the per-user and global limits.
5. GET /api/report returns a plain self-contained HTML evidence pack as in section 8.
6. eval/run_grounding_eval.py with 20 questions including unanswerable ones, with the call-count and cost gate; append its table to eval/RESULTS.md after I say "go".
Commit after each item. Stop and show me one answerable and one unanswerable question working.
```

**You verify:** an unanswerable question is refused; the report says "possible change", never "cheating"; `git tag phase-4`.

---

## Phase 5: Front end and sample mode (Sun 11 Oct, about 8 hours)

**Goal:** the floor works end to end. The clickable prototype is the design reference. Skill: `grounding-audit`.

**Step A: screens (about 5 hours)**

```
Read CLAUDE.md and REQUIREMENTS.md sections 4, 9 and 10, and ROADMAP.md Solo overrides. Do step A of Phase 5 only. Work in frontend/. Plain HTML, CSS and vanilla JavaScript, mobile-first, minimal, no build step, system fonts, the Firebase web SDK only.
1. One small api.js module that sends the Firebase ID token and handles every error and loading state in one place.
2. Screens FE-1 to FE-12 from the document, using the real API: first screen with "Try with sample screenshots" and "Upload my screenshots"; table matching the screen type with yellow low-confidence cells; rejected screens with a clear reason; km and hours inputs for weekly mode; costs; results with BOTH hourly rates and a one-line explanation; changes; ask with a verified label; evidence pack; delete.
3. UI labels in English only, all kept in one strings file (frontend/strings.js) so a language can be added later. No language switcher for now.
Commit per screen. Stop and tell me how to test on my phone.
```

**Step B: sample mode (about 1.5 hours)**

```
Read REQUIREMENTS.md FE-2 and section 19 rule 5. Add sample mode: curate about 6 simulated images (a trip screen, a weekly screen, one order offer) into frontend/samples/ with a small index file, and make the "Try with sample screenshots" button run the REAL flow end to end with them. Cache the extraction result for these sample images only in a shared Firestore collection so repeat visitors cost nothing after the first run. A visitor must complete the flow in a private window with no sign-up. Commit.
```

**You verify:** the floor, step by step, in a private window on your phone over mobile data; `git tag phase-5`. **Checkpoint Sun 11 Oct night.**

---

## Phase 6: Test and harden (Mon 12 to Wed 14 Oct)

**Goal:** real numbers in `eval/RESULTS.md` and a demo that never fails. Skills: `eval-report`, `demo-rehearsal`, `deploy-check`, `grounding-audit`.

**Mon 12 Oct.** Run acceptance scenarios A1 to A10 and A13 from `REQUIREMENTS.md` section 16 and list what fails. Privacy test: delete data, confirm Firestore is empty; confirm no image is stored (check logs and Cloud Storage). Run `grounding-audit`.

**Tue 13 Oct (paste into Claude Code):**

```
Read CLAUDE.md and REQUIREMENTS.md sections 12, 13, 16 and 19, and ROADMAP.md Solo overrides. Do this part of Phase 6 only.
1. Scale the simulated set to 40 labelled screenshots and 20 histories. Before running anything that calls Gemini, print the number of calls and the estimated cost and wait for my "go". Then run all evaluation scripts, including a latency script against the deployed app (ask me for the URL); update eval/RESULTS.md with real numbers, failure types and honest notes on weak spots.
2. Fix the top 3 failure types without special-casing the test images.
3. Friendly handling for: oversized image, unreadable image, non-earnings image, network failure, Gemini timeout, over-limit.
Commit after each item. Stop and show me RESULTS.md.
```

**Wed 14 Oct (paste into Claude Code):**

```
Do the last part of Phase 6. Write docs/DEMO.md with the exact demo steps and timings for a video of at most 3 minutes (aim for 2:50) using only sample data. Add structured logging without images or personal data. Measure the Cloud Run cold-start time and tell me the number. Then stop.
```

**You do:** run the demo path three times in a row with no failures; decide on minimum instances from the cold-start number (minimum instances 1 costs money, so use it only for recording, or for evaluation if cold starts hurt and the cost is acceptable); add a Cloud Monitoring uptime check on `/health`; check the billing alert and, if the account is a free trial, its expiry date; **`git tag v1.0` on 14 Oct (feature freeze)**.

---

## Phase 7 (separate, after the prototype works): docs, deck, video, form (Thu 15 to Sat 17 Oct)

Done in a separate session. Contents, for planning:

- README, ARCHITECTURE.md, a submission description of at most 1,024 characters naming Firebase, Firestore, Cloud Run and Gemini with the real evaluation numbers, a secrets scan.
- Deck: official template, slides 9, 10, 11 and 13 filled with the real cost, screenshots, results and links; PDF under 5 MB.
- Demo video: up to 3 minutes (confirmed by Hack2skill), recorded on the deployed URL with sample data only, uploaded as unlisted.
- Challenge track chosen after reading both descriptions; run the `submission-check` skill; submit on Sat 17 Oct.

**After submitting:** do not redeploy risky changes. There are no retries if the app is down during evaluation.

---

## Stretch: a regional language (decide on 11 or 12 Oct, only if the floor works)

Only if you can personally check every string. Order of steps, cheapest first:

1. Add simulated screenshots in that language to the extraction test, to show "reads screenshots in any language".
2. Let answers come back in that language through the `language` parameter, with the verifier extended to that language's numerals.
3. Translate the UI labels (about 40 strings) only if time remains.

Record the chosen language in `PROGRESS.md` first.

---

## If you fall behind, cut in this order

1. Any regional language (already cut) and the Listen feature (already cut)
2. Editing of table rows (a read-only confirm table is acceptable)
3. Weekly mode UI polish (keep the numbers)
4. The evidence pack styling
5. UI polish generally (UX is 10% of the score)
6. Evaluation set size (keep at least 20 images, and say so honestly)
7. **Never cut:** the live link, the sample button, the number verifier, privacy and delete, the evaluation tables, the cost limits

## Daily rhythm

- 10-minute plan at the start of each session: which prompt, what "done" looks like
- Commit at least once a day; run `phase-check` before tagging
- Update `PROGRESS.md` at the end of each session
- Check the billing dashboard and the live app every day from 14 Oct onward