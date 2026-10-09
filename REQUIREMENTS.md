# PayProof: product and build requirements (v3, 6 Oct 2026)

> This is the document Claude Code builds against. `CLAUDE.md` holds the short always-on rules; `ROADMAP.md` holds the phase order and paste-ready prompts. Where this file says "must", it is a requirement; "should" is a strong preference; "could" is optional.
> Placeholders: `[PROJECT_ID]`, `[REGION]`, `[GITHUB_USERNAME]`, `[EXTRACTION_MODEL]`, `[EXPLAIN_MODEL]`. Always verify current Google GenAI SDK usage and Gemini model names in the official documentation before coding.

## 0. Project facts (v3)

| Item | Value |
|---|---|
| Google Cloud and Firebase project | `payproof-nithin-2026` (billing is on) |
| Region | `asia-south1` for Cloud Run and Firestore. Firestore already exists (native mode, Standard edition) |
| Vertex AI location | `asia-south1` unless the chosen Gemini models are unavailable there; keep it configurable (`VERTEX_LOCATION`) and tell the owner |
| Hosting rewrite | Firebase Hosting can rewrite to Cloud Run only in certain regions. Check the current Firebase documentation; if `asia-south1` is not supported, propose a supported Cloud Run region |
| Credits | **None are provided by the hackathon.** We pay for usage, so cost controls are a requirement (section 19) |
| Gemini backends | `aistudio` (API key, local tests, simulated images only) and `vertex` (deployed app). The $300 free-trial credit, if it applies, cannot pay for AI Studio Gemini costs, and the AI Studio free tier may use content to improve Google products, so the deployed app must use Vertex AI |
| Language scope | **English only for now.** A regional language is a future stretch goal; keep user-visible text in one strings file and a `language` API parameter (default `en`) so one can be added later |
| Owner's machine | Windows, PowerShell, VS Code. Give PowerShell commands, never bash. Python 3.13: report any dependency that does not support it |
| Demo video | Up to 3 minutes (confirmed by Hack2skill support) |
| Evaluation window | 19 Oct to 6 Nov; Top 50 announced 7 Nov. The app must stay live |

## 1. Goal, users and success

**PayProof** shows a gig worker (delivery or ride-hail) what they really earn, using only screenshots they already have.

| Item | Definition |
|---|---|
| Primary user | A gig worker on a phone, with limited patience for forms. A regional language is a possible future addition, not built now |
| Evaluator (equally important) | A hackathon judge who opens our public link once, possibly with no real gig screenshots, and must see it work within a minute |
| Core promise | True net pay per hour and per km after the worker's own costs, with every number exact and checkable |
| Golden rule | Gemini reads and explains. Fixed formulas do all the arithmetic. No number reaches the user unless the engine produced it |
| Success for the submission | A live link that works for every judge, a public repo, a video that shows the working flow, honest evaluation numbers, all four Google services used for real |

Judging weights: technical merit and Gen AI implementation 40%, problem alignment and impact 25%, innovation and creativity 25%, UX and solution design 10%.

## 2. Scope

| Priority | Item |
|---|---|
| **Must** | Screenshot reading for three earnings screen types; reject non-earnings screens; confirm-and-edit table; worker costs input |
| **Must** | Engine in two modes: per-trip and weekly summary; both hourly rates where data allows; pay per km; deduction share |
| **Must** | Pay-change signal (trip mode: bootstrap; weekly mode: simple comparison), with "not enough data" and "cannot tell" states |
| **Must** | Grounded answers with the number verifier and refusals, in English |
| **Must** | Evidence pack (HTML), delete-all-my-data, privacy by design |
| **Must** | **Try with sample screenshots** button so a judge can run the full flow with one tap |
| **Must** | Firebase Hosting and Authentication, Firestore, Cloud Run, Gemini, all in use |
| **Must** | Per-user and global usage limits to protect budget and quota |
| **Should** | Evaluation on 60 to 80 simulated screenshots plus simulated histories, published in `eval/RESULTS.md` |
| **Could** | A regional language (Hindi or Tamil, undecided): screenshots, then answers, then labels; only after the floor works (see ROADMAP.md "Stretch") |
| **Could** | "Listen" button: Gemini text to speech of a verified answer (section 7.4) |
| **Won't** | Reinforcement learning, quantum packages, scraping or automating any real app, loans or credit scoring, advice on where to drive, using the AI Studio free tier in the deployed app |

## 3. Input screen types

Real rider apps show very different screens. We support these `screen_type` values:

| `screen_type` | What it is | What we do |
|---|---|---|
| `trip_detail` | One finished trip with its pay breakdown | Extract one trip |
| `trip_list` | A list of finished trips | Extract many trips |
| `payout_summary` | A weekly payout screen: week range, category amounts (for example order earnings, incentive), total credited, credit date | Extract a `PayoutSummary` |
| `order_offer` | A "new order" screen with expected earning, pickup distance, drop distance, pickup place | **Reject.** An expected earning is a promise, not pay. Return no data and tell the user why |
| `other` | Anything else | Reject with a friendly message |

Important observations from real rider screens:
- A weekly payout screen usually has **no per-trip data, no distance and no minutes**. That is why weekly mode exists (section 5.2).
- An order-offer screen shows distances and an address, which tempts a model to treat them as trip data. Our prompt and tests must prevent that.
- Never copy any real platform's logo, colours, wording or layout. We copy only the list of fields shown.

## 4. Data contracts

### 4.1 `extraction/schema.py`

```python
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

ScreenType = Literal["trip_detail", "trip_list", "payout_summary", "order_offer", "other"]

# Constrained to the real field names (added 9 Oct 2026, Phase 2 hard-tier
# evaluation): the model sometimes wrote a human label ("Base pay") here
# instead of the field name. response_schema enforcement now makes that
# impossible; extraction/extract.py also normalizes any legacy/non-compliant
# label as a backstop.
TripField = Literal["trip_date", "order_id", "order_type", "base_pay", "incentive", "tip", "total_payout", "distance_km", "duration_min"]
PayoutField = Literal["period_label", "period_start", "period_end", "total_credited", "credited_on"]

class Deduction(BaseModel):
    label: str = Field(description="Deduction name exactly as shown")
    amount: float = Field(ge=0, description="Positive number")

class Trip(BaseModel):
    trip_date: Optional[str] = Field(None, description="YYYY-MM-DD only if fully visible")
    order_id: Optional[str] = None
    order_type: Optional[str] = None
    base_pay: Optional[float] = Field(None, ge=0)
    incentive: Optional[float] = Field(None, ge=0)
    tip: Optional[float] = Field(None, ge=0)
    deductions: List[Deduction] = []
    total_payout: Optional[float] = Field(None, ge=0)
    distance_km: Optional[float] = Field(None, ge=0)
    duration_min: Optional[float] = Field(None, ge=0)
    low_confidence_fields: List[TripField] = []

class PayoutLine(BaseModel):
    label: str = Field(description="Earning or incentive name exactly as shown")
    amount: float = Field(ge=0)

class PayoutSummary(BaseModel):
    period_label: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    lines: List[PayoutLine] = []
    deductions: List[Deduction] = []
    total_credited: Optional[float] = Field(None, ge=0)
    credited_on: Optional[str] = None
    low_confidence_fields: List[PayoutField] = []

class ExtractionResult(BaseModel):
    platform_label: Optional[str] = None
    currency: Optional[str] = None
    language_detected: Optional[str] = None
    screen_type: ScreenType
    trips: List[Trip] = []
    payout_summary: Optional[PayoutSummary] = None
    needs_review: bool
    notes: Optional[str] = Field(None, description="Short reason when the screen is rejected")
```

### 4.2 Stored documents (Firestore, under the signed-in user's id)

- `users/{uid}/trips/{trip_id}`: confirmed trip rows.
- `users/{uid}/weeks/{week_id}`: confirmed weekly summaries plus the worker's km and hours for that week.
- `users/{uid}/costs/current`: `fuel_cost_per_km`, `maintenance_cost_per_km`, optional `fixed_cost_per_day`.
- `users/{uid}/answers/{answer_id}`: verified answers (text, language, numbers used) so that text to speech can only speak verified text.
- Never store images, names, phone numbers or addresses.

## 5. Engine requirements (`engine/`, pure Python, no network calls, no LLM)

General rules: return `None`, never zero, when a denominator is zero or data is missing. Reject negative inputs. Include `data_quality` notes (missing distance, missing duration, reconciliation flags). All thresholds live in `config.py`.

### 5.1 Trip mode

| Term | Formula |
|---|---|
| `gross_pay` | sum over trips of `base_pay + incentive + tip` (nulls count as 0 and are counted as missing) |
| `platform_deductions` | sum of all deduction amounts |
| `net_payout` | `gross_pay - platform_deductions` |
| `reconciliation_gap` | per trip, `(base+incentive+tip-deductions) - total_payout` when `total_payout` is present; flag if absolute gap > 0.5 |
| `worker_costs` | `total_distance_km * (fuel_cost_per_km + maintenance_cost_per_km)` + fixed costs per day in the period |
| `net_earnings` | `net_payout - worker_costs` |
| `engaged_hours` | `sum(duration_min) / 60` |
| `net_per_engaged_hour` | `net_earnings / engaged_hours` |
| `net_per_logged_in_hour` | `net_earnings / logged_in_hours` (only if the worker entered it) |
| `net_payout_per_km` | `net_payout / total_distance_km` |
| `deduction_share` | `platform_deductions / gross_pay` |

**Worked example (must be a unit test).** Trip 1: base 80, incentive 20, tip 10, fee 10, 5 km, 25 min. Trip 2: base 60, 3 km, 15 min. Fuel 3.0 and maintenance 1.0 per km. Hours online 1.5.
Expected: gross 170; deductions 10; net payout 160; costs 32; net earnings 128; engaged hours 0.6667; per engaged hour 192.00; per logged-in hour 85.33; per km 20.00; deduction share 0.0588.

### 5.2 Weekly mode

Inputs: confirmed `PayoutSummary`, plus worker-entered `km_driven` and `hours_online` for that week, plus cost inputs.

| Term | Formula |
|---|---|
| `gross_weekly` | sum of `lines` amounts |
| `deductions_weekly` | sum of deductions |
| `net_payout_weekly` | `gross_weekly - deductions_weekly` |
| `reconciliation_gap` | `total_credited - net_payout_weekly` when `total_credited` is present; flag if absolute gap > 0.5 |
| `worker_costs_weekly` | `km_driven * (fuel + maintenance)` + fixed costs for the days in the week |
| `net_earnings_weekly` | `net_payout_weekly - worker_costs_weekly` |
| `net_per_online_hour` | `net_earnings_weekly / hours_online` |
| `net_payout_per_km` | `net_payout_weekly / km_driven` |
| `deduction_share` | `deductions_weekly / gross_weekly` |

Per-hour-on-trips is **not available** in weekly mode (no trip minutes); the UI must say so instead of showing a blank.

**Worked example (must be a unit test).** Lines: order earnings 7,000 and daily incentive 1,500. Deduction: platform charges 300. Total credited 8,200. Worker enters 520 km and 48 hours online; fuel 3.0, maintenance 1.0.
Expected: gross 8,500; deductions 300; net payout 8,200; reconciliation gap 0; costs 2,080; net earnings 6,120; net per online hour 127.50; per km 15.77; deduction share 0.0353.

### 5.3 Pay-change signal

**Trip mode (`engine/changes.py`)**
- Split trips into baseline and recent periods (ISO week or user-chosen split date).
- Metrics per trip: `net_payout_per_km`, net payout per engaged hour, `deduction_share`.
- Require at least 15 trips per period; otherwise status `insufficient_data` with the counts.
- Seeded bootstrap (10,000 resamples, fixed seed) for the 95% range of the difference in means.
- `possible_change` only if the range excludes 0 and the relative change is at least 5%; else `no_clear_change`.

**Weekly mode (`engine/weekly.py`)**
- Require at least 3 earlier weeks plus the latest week; otherwise `insufficient_data`.
- Compare the latest `net_per_online_hour` with the mean of the earlier weeks.
- `possible_change` if the absolute relative change is at least 10% (configurable); else `no_clear_change`.
- This is a simple comparison, not a statistical test. The UI wording is "lower (or higher) than your usual by X%". Never say "significant".

Wording rule for both: "possible change" or "no clear change", never "cheating", "fraud" or "proof".

## 6. Extraction requirements

- Gemini through the single client module (`GEMINI_BACKEND`: `aistudio` locally with simulated images only, `vertex` when deployed), structured JSON output against `ExtractionResult`, temperature 0. Use the cheapest model that meets accuracy (section 19), and tell the owner which model and the approximate cost per call.
- The system prompt must say: copy only what is visible; null when not shown; never calculate totals or rates; amounts as plain numbers; keep labels as written; ISO dates only if fully visible; **do not extract names, phone numbers or addresses**; mark unclear fields in `low_confidence_fields` and set `needs_review`; for an order-offer screen return `screen_type="order_offer"`, no trips, and a note; for any non-earnings screen return `other`.
- **Exactly one Gemini call per screenshot**, plus at most one retry on invalid output, then return `needs_review=true` with a safe message. Never loop. Never show raw model output.
- A 429 from Vertex AI or the Gemini API means the request was **not processed** (not a bad screenshot). Handle it with at most 2 short randomised pauses (jittered backoff), counted separately from the one schema-invalid-output retry above, then a friendly "PayProof is busy right now, please try again in a minute" message. Never loop beyond that. (Confirmed in practice: Vertex AI returned its own `429 RESOURCE_EXHAUSTED` during evaluation, a different quota from the AI Studio free tier's 15 requests/minute/model limit.)
- Before sending an image, resize it on the server to at most `IMAGE_MAX_SIDE_PX` on the longest side, re-encode as JPEG at `IMAGE_JPEG_QUALITY`, and strip metadata (section 19). Check that accuracy does not drop.
- Images are processed in memory only, never written to disk, Cloud Storage or logs. Limit size (suggested 8 MB) and types (PNG, JPEG, WebP); reject others with a friendly message. Set a timeout and handle it.
- Multiple screenshots may be uploaded in one go; process them one at a time with a visible progress state.

## 7. Grounded answers

### 7.1 Tools

Gemini uses function calling with read-only tools that return engine results: `get_summary()`, `get_changes()`, `get_trip_stats()`, `get_weekly()`. The model may state only numbers those tools returned.

### 7.2 Number verifier (`backend/qa.py`)

1. Extract every number from the draft answer, including percentages and numbers written with Indian digit grouping (for example 1,23,456). Numerals of other languages are handled only if a regional language is added later.
2. Check each against the tool outputs, allowing rounding to 2 decimals and percentage forms.
3. On any mismatch, regenerate once with a stricter instruction; if it still fails, return a refusal that names what is missing.
4. Unit-test it with passing, failing and edge cases (no network calls).

### 7.3 Refusals

If data cannot answer the question (no hours online, too few trips, weekly mode asked for per-trip-hour), say so plainly and say what is missing. Never guess.

### 7.4 Optional "Listen" (text to speech)

- Only after the core is complete. Use Gemini text to speech through the Cloud Text-to-Speech API or Vertex AI; documentation lists Hindi (India) and Tamil (India) as generally available. Verify the current model names, English availability and regional support before coding.
- The endpoint takes an `answer_id` of a stored **verified** answer, never free text, so unverified text can never be spoken.
- A native speaker must listen to numbers and rupee amounts in each language before we keep the feature.
- Cut this feature first if the schedule slips.

## 8. Evidence pack

A self-contained HTML page with: header (generated by PayProof, period, data source), summary table, the method (the formulas in words), data-quality notes, limits ("built only from screenshots the worker provided; a change flag is a signal, not proof"), and the date. No names or phone numbers. A print-friendly style.

## 9. Frontend requirements

Plain HTML, CSS and vanilla JavaScript in `frontend/`, mobile-first, minimal. No build step. Use system fonts and the Firebase web SDK only. The clickable prototype (7 screens) is the design reference: Upload, Check the table, Costs, Real pay, Pay changes, Ask, Evidence pack.

| ID | Requirement |
|---|---|
| FE-1 | First screen: one sentence on what PayProof does, **"Try with sample screenshots"** and "Upload my screenshots". Sign-in is automatic (anonymous); the judge never creates an account |
| FE-2 | Sample mode loads curated simulated screenshots from `frontend/samples/` (trip, weekly, an order offer to show rejection) and runs the real flow end to end |
| FE-3 | After extraction, show a table matching the screen type: trips table or weekly table. Highlight low-confidence cells in yellow. Rows can be edited, added and deleted. Nothing is calculated until the user confirms. Show the worker's own uploaded screenshot (a client-side preview, generated in the browser from the file the worker just chose, never uploaded or stored anywhere) next to the extracted table, with the text "Check these numbers against your screenshot" — the final guard against a confident wrong number, added 9 Oct 2026 after the hard-tier evaluation found the model sometimes returns a wrong value instead of null even when flagged for review |
| FE-4 | Rejected screens (order offer, other) show a clear message explaining why, with no table |
| FE-5 | Weekly mode asks for km driven and hours online for that week; trip mode asks for optional hours online |
| FE-6 | Costs screen: fuel per km, maintenance per km, optional fixed daily cost, with a short "why we ask" line |
| FE-7 | Results: net earnings; both hourly rates where available, clearly labelled, with a one-line explanation of why they differ; pay per km; deduction share; data-quality notes; "not available in weekly mode" where relevant |
| FE-8 | Changes: possible change, no clear change or not enough data, with the numbers and, in trip mode, the range |
| FE-9 | Ask: answer with the numbers it used and a "verified" label, refusal shown plainly |
| FE-10 | Evidence pack download; visible privacy note; "Delete all my data" that works |
| FE-11 | UI labels in English only, all kept in one strings file (`frontend/strings.js`) so a language can be added later; no language switcher for now |
| FE-12 | Every network step has loading, error and retry states; no raw errors, no blank screens |
| FE-13 | Tap targets at least 44 px; text contrast at least 4.5:1; works on a current Chrome for Android over a slow network |
| FE-14 | Never show a number the API did not return |

## 10. Backend and API

| Method and path | Purpose | Auth |
|---|---|---|
| `GET /health` | health check | none |
| `POST /api/extract` | multipart image in, `ExtractionResult` out | Firebase token |
| `PUT /api/trips` | save confirmed trips | token |
| `PUT /api/weeks` | save confirmed weekly summary with km and hours | token |
| `PUT /api/costs` | save cost inputs | token |
| `GET /api/summary` | engine summary (trip or weekly mode) | token |
| `GET /api/changes` | pay-change signal | token |
| `POST /api/ask` | `{question, language}` returns a verified answer with `answer_id` | token |
| `POST /api/tts` | optional; `{answer_id}` returns audio | token |
| `GET /api/report` | evidence pack HTML | token |
| `DELETE /api/data` | delete everything for this user | token |

- The user id always comes from the verified Firebase token, never from the path or body.
- Errors use one JSON shape: `{error_code, message, detail?}`; messages are user-safe.
- **Usage limits** (configurable; defaults 12 extractions and 25 questions per user per day, and a global cap of 400 Gemini calls per day), kept as atomic counters in Firestore, to protect budget and quota during judging. Over-limit returns a friendly message, not a crash.
- Log token counts per Gemini call (counts only, never content, images or personal data) so the owner can watch cost.
- Structured logs without images or personal data.

## 11. Security and privacy

- Firebase ID token verified (`firebase-admin`) on every `/api` route except `/health`.
- Firestore security rules: a user can read and write only their own documents.
- Secrets only in environment variables or Secret Manager; `.env` is git-ignored; `.env.example` lists names only. Never print, read back or commit `.env`. The AI Studio key is for local use only and is left empty on Cloud Run, where Vertex AI uses the service account (no key files).
- The Firebase web config (apiKey, authDomain, projectId, appId) is not secret and may live in `frontend/firebase-config.js`.
- Least-privilege service account roles for Vertex AI and Firestore.
- No images stored anywhere; no names, phone numbers or addresses extracted.
- Demos, tests and docs use fictional platforms and simulated data only.
- A visible privacy note and a working delete function.

## 12. Simulation requirements (`eval/generate_data.py`, `docs/SIMULATION.md`)

"Simulate" means we invent the trips and weeks, then draw the screens ourselves, so we know the right answer in advance. We simulate the receipt, not the delivery: no maps, routes or addresses.

**Layouts (fictional apps only)**

| Layout | Type | Fields | Purpose |
|---|---|---|---|
| L1 trip detail card | positive | base, incentive, tip, deduction lines, total, km, minutes | main per-trip case |
| L2 trip list | positive | date, km, pay per row (some variants omit minutes) | multiple trips; missing-field tests |
| L3 weekly payout | positive | week range, headline credited total, category rows, credited date | weekly mode |
| N1 order offer | negative | expected earning, pickup km, drop km, a pickup place and address | must be rejected |
| N2 other screen | negative | settings or help screen | must be rejected |

**Languages:** English only for now. Use a free font and record where it came from and its licence. A regional language (with the matching Noto font) is a later stretch.
**Noise:** blur, slight rotation, partial crop, dark mode, JPEG compression, and low brightness.
**Ground truth:** a JSON file beside every image, validated against the schema.
**Value ranges** (assumptions for testing, stored in `config`): distance 0.5 to 12 km; minutes from distance plus a waiting term; base pay from a fixed amount plus a per-km rate with random variation; occasional tips and incentives; occasional deductions. A fixed seed makes everything repeatable.
**Histories:** 40 simulated trip histories (six weeks; half with a 10% per-km pay cut from week 4) and 40 simulated weekly histories (eight weeks; half with a 12% drop from week 6).
**Counts:** 60 to 80 labelled screenshots in the main set, plus the curated sample set in `frontend/samples/`.
**Brand safety:** a deny list of real platform names is checked before any file is written. Do not copy any real design.
**Real screenshots:** if a teammate collects any, they must have the rider's consent, names and phone numbers blurred, be kept private, and stay out of the public repo, the deck and the video. They are never part of the accuracy numbers.

## 13. Evaluation requirements (`eval/`)

| Script | Measures | Output |
|---|---|---|
| `run_extraction_eval.py` | Field-level accuracy by screen type, layout and noise; rejection rate of order-offer and other screens; `needs_review` precision on bad images | table in `eval/RESULTS.md` |
| `run_change_eval.py` | Precision, recall and false-alarm rate for trip mode and weekly mode on injected versus stable histories | table |
| `run_grounding_eval.py` | 30 questions including unanswerable ones: share of answers whose numbers all come from the engine, and share of correct refusals | table |
| latency script | Seconds per screenshot and per answer on the deployed app | table |

Report real numbers, including weak ones, with the date, counts and model names. Never edit numbers by hand and never tune prompts to specific test images.

**Cost gate:** every script that calls Gemini must print the number of calls and the estimated cost BEFORE running and wait for the owner's "go". Unit tests use mocked model output with no network calls.

## 14. Deployment and operations

- Cloud Run: FastAPI service `payproof` in `asia-south1` (or the region the Hosting rewrite supports), `--max-instances=3`, minimum instances 0 for now, request timeout about 60 s, 1 GiB memory (adjust after testing), `--allow-unauthenticated` at the network level with app-level token checks. Keep the previous revision available for rollback.
- Firebase Hosting: `frontend/` served publicly, with `/api/**` rewritten to the Cloud Run service. The Hosting URL is the **prototype link** we submit.
- **Keep it live.** The roadmap shows prototype evaluation from 19 Oct to 6 Nov and the Top 50 announcement on 7 Nov. The app must be up, with working Gemini, Firestore and sign-in, until at least 7 Nov, and longer if we are shortlisted. Measure the cold-start time on 14 Oct. Set minimum instances to 1 only for recording, and for the evaluation window only if cold starts are a problem and the cost is acceptable to the owner. Set billing budget alerts; add a Cloud Monitoring uptime check on `/health`; check the live app daily. If the billing account is a free trial, note its expiry date and upgrade to a paid account before it, or the app stops.
- Deploy only from `main`, only after tests pass, and only with the owner's approval.

## 15. Repository and documentation

- New public repo; first commit after the programme launch; frequent small commits.
- `README.md`: problem, solution, architecture (how Firebase Hosting, Firebase Authentication, Firestore, Cloud Run and Gemini are used), how to run locally, evaluation results, limits, privacy.
- `docs/ARCHITECTURE.md` with a Mermaid diagram, `docs/SIMULATION.md`, `docs/DEMO.md`, `docs/submission_description.md` (at most 1,024 characters, naming all four Google services and the real evaluation numbers).
- `PROGRESS.md` updated at the end of each phase.

## 16. Acceptance scenarios

| ID | Scenario | Expected result |
|---|---|---|
| A1 | Trip-detail screenshot in English, then costs | Table matches ground truth; results equal the worked example |
| A2 | Weekly payout screenshot in English, then km and hours | Weekly table; results equal the weekly worked example (127.50 per online hour, 15.77 per km) |
| A3 | Order-offer screenshot | Rejected with a clear reason; no numbers taken from it |
| A4 | Blurred or cropped screenshot | `needs_review` true; unclear cells highlighted |
| A5 | Six-week trip history with a 10% cut, and a stable one | "Possible change" for the first, "no clear change" for the second |
| A6 | Fewer than 15 trips in a period | "Not enough data" |
| A7 | One answerable and one unanswerable question | Verified answer; plain refusal |
| A8 | Draft answer containing a number the engine did not produce (test hook) | Verifier blocks it |
| A9 | Delete all data | Firestore documents gone; API returns nothing for that user |
| A10 | New visitor in a private window taps the sample button | Full flow completes with no sign-up, in under 60 seconds on a normal connection (measure and report; do not claim before measuring) |
| A11 | User B requests user A's data | Rejected |
| A12 | Daily limit exceeded | Friendly message, no crash |
| A13 | One screenshot through the live app | Logs show exactly one Gemini call (or two with the one retry) and its token counts; no image or personal data in the logs |

## 17. Non-functional targets (measure, then report; do not claim before measuring)

- Extraction latency per screenshot and answer latency: measure on the deployed app.
- No unhandled exceptions on the demo path; three clean runs in a row before recording.
- Works on a current Chrome for Android over a slow connection.

## 18. Open decisions

| Decision | Options | Decide by |
|---|---|---|
| Challenge track | Sustainability and Social Impact, or Future of Work and Enterprise Productivity; read both descriptions | 14 Oct |
| Regional language (stretch) | Not now. Decide after the floor works, only if the owner can check every string | 11 to 12 Oct |
| Video length | **Settled:** up to 3 minutes (Hack2skill support). Aim for 2:50 and never exceed 3:00 | done |
| Cloud Run region | `asia-south1`, unless Hosting cannot rewrite to it; Claude Code checks the documentation and the owner approves | Phase 1 |
| Gemini models | Claude Code checks current documentation and pricing, proposes the cheapest model that meets accuracy; the owner approves | Phase 2 |
| "Listen" feature | Build only if the core is finished by 11 Oct | 11 Oct |

## 19. AI cost controls (we pay for every Gemini call)

1. Check the current Vertex AI and Gemini documentation and pricing, pick the cheapest model that meets accuracy for extraction, and tell the owner the model names and the approximate cost per call. Keep model names in environment variables. Treat any price you read as unverified until the owner checks the pricing page.
2. Exactly one Gemini call per screenshot; at most one retry on invalid output; never loop.
3. Resize images before sending: longest side at most `IMAGE_MAX_SIDE_PX` (default 1280), JPEG at `IMAGE_JPEG_QUALITY` (default 85), metadata stripped. Make both configurable and check that accuracy does not drop.
4. Cap output: about `EXTRACTION_MAX_OUTPUT_TOKENS` (1,500) for extraction and `ANSWER_MAX_OUTPUT_TOKENS` (400) for answers. Temperature 0. Turn off or minimise any "thinking" mode if the API allows it. Keep prompts short.
5. Cache extraction results by image hash for the current session. For the curated SAMPLE images only (simulated, never user uploads), cache results in a shared Firestore collection, so repeat visitors tapping "Try with sample screenshots" cost zero Gemini calls after the first run, while still running the real flow end to end.
6. Q&A: pass only compact engine JSON to Gemini, never images or long histories. At most two model calls per question (the draft, plus one retry after the verifier). The verifier is plain code.
7. Usage limits as in section 10, enforced with atomic Firestore counters.
8. Log token counts per call (counts only).
9. Tests use mocked Gemini output. Evaluation scripts print the number of Gemini calls and the estimated cost first and wait for the owner's "go".
10. Cloud Run: `--max-instances=3`; minimum instances 0 until the 14 Oct cold-start decision.
11. A billing budget alert must exist before the first deploy. It warns but does not stop spending, so the in-app limits are the real guard.
12. A 429 (rate-limit/quota-exhausted) response means the request was **not processed**. Retry with at most 2 short randomised pauses, counted separately from the one schema-invalid-output retry in rule 2, then a friendly "busy, try again" message — never loop beyond that. Both AI Studio (15 requests/minute/model on the free tier) and Vertex AI (its own, separate per-project quota) have been observed returning 429s during evaluation; the two are different limits and neither is a signal to switch model, backend or region on your own.

## 20. Environment variables (`.env.example` lists these; never commit `.env`)

| Variable | Purpose | Default |
|---|---|---|
| `PROJECT_ID` | Google Cloud project | `payproof-nithin-2026` |
| `REGION` | Cloud Run and Firestore region | `asia-south1` |
| `VERTEX_LOCATION` | Vertex AI location | `asia-south1` |
| `GEMINI_BACKEND` | `aistudio` (local, simulated images only) or `vertex` (deployed) | `aistudio` locally |
| `GEMINI_API_KEY` | AI Studio key, local only; empty on Cloud Run | empty |
| `EXTRACTION_MODEL`, `EXPLAIN_MODEL` | Model names chosen after reading current docs and pricing | set in Phase 2 |
| `IMAGE_MAX_SIDE_PX`, `IMAGE_JPEG_QUALITY`, `MAX_UPLOAD_MB` | Image preparation and upload limit | 1280, 85, 8 |
| `EXTRACTION_MAX_OUTPUT_TOKENS`, `ANSWER_MAX_OUTPUT_TOKENS` | Output caps | 1500, 400 |
| `GEMINI_TIMEOUT_SECONDS` | Per-call timeout | 30 |
| `LIMIT_EXTRACTIONS_PER_USER_PER_DAY`, `LIMIT_QUESTIONS_PER_USER_PER_DAY`, `LIMIT_GLOBAL_GEMINI_CALLS_PER_DAY` | Usage limits | 12, 25, 400 |
| `QUALITY_MIN_SHORT_SIDE_PX`, `QUALITY_MIN_SHARPNESS`, `QUALITY_MIN_CONTRAST`, `QUALITY_MIN_BRIGHTNESS`, `QUALITY_MAX_BRIGHTNESS` | Image-quality gate before any Gemini call (extraction/image_quality.py); tuned on simulated data only, not validated on real screenshots | 300, 3.9, 10.0, 15.0, 254.0 |