# PayProof: always-on rules for Claude Code

PayProof tells gig workers (delivery and ride-hail) what they really earn per hour after their own costs, from screenshots they already have. Gemini reads and explains; fixed formulas do every calculation.
This is our entry for the Google Cloud AI Builder Cup 2026. Submission closes 18 Oct 2026, 11:59 PM IST; we submit on 17 Oct. One person builds it alone, alongside a day job, so time is the scarcest resource.

## Where things are

- `REQUIREMENTS.md`: what to build (project facts in section 0, data contracts, formulas, screens, API, simulation, evaluation, acceptance tests, AI cost controls in section 19, environment variables in section 20). Read the relevant section before each task.
- `ROADMAP.md`: the phase order, dates, checkpoints and paste-ready prompts. **Its "Solo overrides" win over `REQUIREMENTS.md` where they conflict.**
- `.claude/skills/`: skills you can use (listed below).
- `PROGRESS.md`: running log. Update it at the end of every session, with the exact commands to resume.

## Project facts

- Google Cloud and Firebase project id: `payproof-nithin-2026`. Billing is on. **No hackathon credits are provided, so we pay for usage.** The owner must keep a billing budget alert set.
- Region for Cloud Run and Firestore: `asia-south1`. Firestore already exists (native mode, Standard edition). Vertex AI location: `asia-south1` unless the chosen Gemini models are unavailable there; keep it configurable as `VERTEX_LOCATION` and tell the owner. Check whether Firebase Hosting can rewrite to Cloud Run in `asia-south1`; if not, propose a supported region.
- Gemini backends: `GEMINI_BACKEND=aistudio` (API key from `.env`; local tests with simulated images only, because the free tier may use content to improve Google products) and `GEMINI_BACKEND=vertex` (the deployed app). The $300 free-trial credit cannot pay for AI Studio Gemini costs, so the deployed app uses Vertex AI. Keep every Gemini call behind one small client module.
- The owner works on Windows with PowerShell and VS Code, Python 3.13. Give PowerShell commands, never bash. Report any dependency that does not support Python 3.13.
- The demo video limit is up to 3 minutes (confirmed by Hack2skill). The video, deck and submission documents are separate work, done after the prototype works.

## Hard rules (never break these)

1. **Fresh project only.** All code is written new in this repo. No code, files or assets from any earlier project. History starts with this repo's first commit.
2. **Gemini never does arithmetic.** Every number shown to the user comes from `engine/`. Gemini extracts, explains and routes questions only. No LLM or network call anywhere in `engine/`.
3. **No guessing.** Unknown or unreadable values are `null` or "cannot tell". Never fill gaps.
4. **Fictional platforms only** in demos, tests, samples and docs. Never copy a real platform's logo, colours, wording or layout. No scraping or automating real apps.
5. **Privacy.** Do not extract names, phone numbers or addresses. Never store uploaded images (memory only). Store only confirmed structured data under the signed-in user's id, with a working delete.
6. **No accusations.** Wording is "possible change" and "no clear change", never "cheating", "fraud" or "proof".
7. **Secrets** live in environment variables or Secret Manager, never in git. Keep `.env` ignored. Never print, read back or commit `.env`, and never ask the owner to paste a secret into chat.
8. **Honest metrics.** Report real evaluation numbers, including weak ones. Never edit a number by hand or tune prompts to specific test images.
9. **Use all four required Google services for real:** Firebase (Hosting and Authentication), Firestore, Cloud Run, Gemini.
10. **The deployed app must stay live and working** through the evaluation period (until at least 7 Nov). Do not delete the project, rotate keys carelessly or exceed quota.
11. **Ask before deploying, pushing, adding a dependency, or changing the spec.**

## AI cost rules (we pay for every Gemini call; full list in REQUIREMENTS.md section 19)

- One Gemini call per screenshot, at most one retry, never loop. Resize images to at most 1280 px and JPEG quality 85 before sending. Cap output tokens, temperature 0, short prompts.
- Q&A: compact engine JSON only, at most two model calls per question. The verifier is plain code.
- Cache sample-image results; enforce per-user and global usage limits with Firestore counters; log token counts only.
- Tests use mocked Gemini output. Any script that calls Gemini prints the call count and estimated cost first and waits for the owner's "go".
- Cloud Run `--max-instances=3`. Pick the cheapest model that meets accuracy and tell the owner the model names and approximate cost; treat prices you read as unverified.

## Where to stop and ask the owner

Before any deploy and any `git push` (show the exact command); when you need a secret (name the `.env` entry, never see the value); before bulk Gemini runs; after the first extraction accuracy table; before a new dependency or any spec change; before any task that would cost more than about an hour and is not on the floor; when the `[LANG_1]` strings are ready to check.

## How we work

- Build the "floor" first (the minimum viable demo in `ROADMAP.md`), deploy it, then widen. Do not polish before the floor works.
- One phase at a time. Start by restating the goal and acceptance criteria; end by running tests, using `phase-check`, updating `PROGRESS.md`, and proposing a commit. Local commits are fine without asking.
- Small commits with clear messages. Run `pytest` before every commit.
- Prefer the simplest thing that satisfies the requirement. Never claim something works unless you ran it; report failures honestly.

## Commands (PowerShell)

- Run locally: `uvicorn backend.main:app --reload` (use `gcloud auth application-default login`)
- Tests: `pytest -q`
- Deploy: use the `deploy-check` skill. Never deploy without the owner's approval.

## Skills available

`phase-check`, `eval-report`, `deploy-check`, `submission-check`, `sim-data`, `grounding-audit`, `demo-rehearsal`. Use them at the points named in `ROADMAP.md`.

## Verify before coding

The Google GenAI SDK and Gemini model names change. Check the current official documentation before writing code that calls Gemini, Vertex AI, Firebase or Text-to-Speech, and tell the owner which model names you chose. Gemini availability can differ by region.
