# PayProof: always-on rules for Claude Code

PayProof tells gig workers (delivery and ride-hail) what they really earn per hour after their own costs, from screenshots they already have. Gemini reads and explains; fixed formulas do every calculation.
This is our entry for the Google Cloud AI Builder Cup 2026. Submission closes 18 Oct 2026, 11:59 PM IST; we submit on 17 Oct.

## Where things are

- `REQUIREMENTS.md`: what to build (data contracts, formulas, screens, API, simulation, evaluation, acceptance tests). Read the relevant section before each task.
- `ROADMAP.md`: the phase order, dates and paste-ready prompts.
- `.claude/skills/`: skills you can use (listed below).
- `PROGRESS.md`: running log. Update it at the end of every phase.

## Hard rules (never break these)

1. **Fresh project only.** All code is written new in this repo. No code, files or assets from any earlier project of the team. History starts with this repo's first commit.
2. **Gemini never does arithmetic.** Every number shown to the user comes from `engine/`. Gemini extracts, explains and routes questions only. No LLM or network call anywhere in `engine/`.
3. **No guessing.** Unknown or unreadable values are `null` or "cannot tell". Never fill gaps.
4. **Fictional platforms only** in demos, tests, samples and docs. Never copy a real platform's logo, colours, wording or layout. No scraping or automating real apps.
5. **Privacy.** Do not extract names, phone numbers or addresses. Never store uploaded images (memory only). Store only confirmed structured data under the signed-in user's id, with a working delete.
6. **No accusations.** Wording is "possible change" and "no clear change", never "cheating", "fraud" or "proof".
7. **Secrets** live in environment variables or Secret Manager, never in git. Keep `.env` ignored.
8. **Honest metrics.** Report real evaluation numbers, including weak ones. Never edit a number by hand or tune prompts to specific test images.
9. **Use all four required Google services for real:** Firebase (Hosting and Authentication), Firestore, Cloud Run, Gemini.
10. **The deployed app must stay live and working** through the evaluation period (until at least 7 Nov). Do not delete the project, rotate keys carelessly or exceed quota.
11. **Ask before deploying, adding a dependency, or changing the spec.**

## How we work

- One phase at a time. Start each phase by restating its goal and acceptance criteria; end by running tests, updating `PROGRESS.md`, and proposing a commit. Stop for review.
- Small commits with clear messages. Run `pytest` before every commit.
- Four people work in parallel on four tracks, each in its own folder and branch. Do not edit another track's folder without asking. The JSON contracts in `REQUIREMENTS.md` section 4 and the API table in section 10 are the interface between tracks.

| Track | Owns | Folders |
|---|---|---|
| A: backend and AI | engine, extraction, Q&A, deployment | `backend/`, `engine/`, `extraction/`, `tests/` |
| B: front end | the screens and sample mode | `frontend/` |
| C: data and evaluation | simulator, labelled data, eval scripts, results | `eval/`, `frontend/samples/` |
| D: research and submission | interviews, deck, video, docs, form text | `docs/`, `README.md` |

## Commands

- Run locally: `uvicorn backend.main:app --reload` (use `gcloud auth application-default login`)
- Tests: `pytest -q`
- Deploy: use the `deploy-check` skill. Never deploy without the owner's approval.

## Skills available

`phase-check`, `eval-report`, `deploy-check`, `submission-check`, `sim-data`, `grounding-audit`, `demo-rehearsal`. Use them at the points named in `ROADMAP.md`.

## Verify before coding

The Google GenAI SDK and Gemini model names change. Check the current official documentation before writing code that calls Gemini, Vertex AI, Firebase or Text-to-Speech, and tell the owner which model names you chose.
