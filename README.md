# PayProof

PayProof tells gig workers (delivery and ride-hail) what they really earn per hour after their own costs, from screenshots they already have. Gemini reads and explains; fixed formulas do every calculation.

Built solo for the Google Cloud AI Builder Cup 2026.

> This README is a stub for Phase 1. Full problem/solution/architecture, local run instructions, evaluation results, limits and privacy notes are written in Phase 7, once the prototype works.

## Status

See `PROGRESS.md` for the current build phase.

## Regions and models (current)

- Cloud Run and Firestore: `asia-south1`.
- Vertex AI (Gemini): `global` — the extraction model isn't available as a regional endpoint in `asia-south1`, only on `global`/`us`/`eu`.
- `EXTRACTION_MODEL=gemini-3.1-flash-lite`, confirmed working identically on both the AI Studio and Vertex AI backends. See `PROGRESS.md` for how this was chosen.

## Local development (Windows, PowerShell)

```powershell
Copy-Item .env.example .env
# fill GEMINI_API_KEY in .env (never commit it)
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Tests:

```powershell
pytest -q
```
