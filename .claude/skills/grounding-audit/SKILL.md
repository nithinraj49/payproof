---
name: grounding-audit
description: Audit that every number PayProof shows or speaks comes from the engine, and that the number verifier and refusals work. Use before integration, before the feature freeze, and whenever the UI or the Q&A code changes.
---

# Grounding audit

The golden rule: Gemini reads and explains; the engine does all the arithmetic. A wrong number in the demo is the biggest risk we have.

## Steps

1. Search `engine/` for any import of an LLM or network library; any hit is a failure.
2. Search `backend/` and `frontend/` for every place a number is formatted or displayed. For each, trace it back to a field in an engine response. List any number that is computed or typed in the front end or the backend outside `engine/`.
3. Read `backend/qa.py`. Confirm tools return engine results only, the verifier runs on every draft answer, there is exactly one retry, and the fallback is a refusal.
4. Run the verifier unit tests. Then try at least five adversarial cases against the verifier or the local API: a wrong number, a rounded number, a percentage, an Indian-grouped number such as 1,23,456, and Hindi or Tamil numerals.
5. Confirm refusals for: no hours online, too few trips, weekly mode asked for a per-trip-hour figure.
6. If text to speech exists, confirm it accepts only an `answer_id` of a stored verified answer and never free text.
7. Search copy and templates for banned words: "cheating", "fraud", "proof of", "significant".

## Output

A table: Check, Result, Evidence (file and line). Do not change code; report and let me decide.
