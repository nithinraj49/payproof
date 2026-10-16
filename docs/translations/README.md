# Translating PayProof

`en.json` is the source: a flat list of key to English text for every word the app shows on screen (140 strings). It is generated from `frontend/strings.js`. Backend-generated text is listed separately in `backend_strings.md`.

## How to translate

1. Copy `en.json` to `<lang>.json` (for example `hi.json`). Keep every key exactly as it is. Change only the text on the right.
2. Run `node scripts/check_translations.js <lang>` and fix everything it reports.

## Rules

- **Keep placeholders unchanged.** Anything in curly braces, such as `{current}`, `{total}`, `{computed}`, `{credited}`, `{gap}`, `{count}`, `{status}`, `{code}`, is filled in by the app. Copy it exactly, spelling and braces included. You may move it to wherever your language needs it in the sentence.
- **Keep the rupee sign (₹) unchanged.** Do not write "Rs", "INR" or "rupees" in its place. No other currency sign is allowed.
- **Numbers stay as digits 0 to 9.** Do not use Devanagari, Tamil or any other numerals.
- **Use simple everyday words**, the way a delivery or ride-hail worker would say it. Not formal banking words.
- Keep the meaning. Do not add or remove warnings. Never use words that accuse a platform of wrongdoing; the app says "possible change" and "no clear change".
- Keep the brand name `PayProof` in Latin letters.
- `results.tripReconciliationNoteOne` is used when exactly 1 trip is affected. `results.tripReconciliationNoteMany` is used for other counts and has `{count}`.
- `ask.suggestionsTrip.N` and `ask.suggestionsWeekly.N` are example questions; write them the way a worker would ask.

## Checker

`node scripts/check_translations.js [lang ...]` compares each `docs/translations/<lang>.json` with `en.json` and reports missing keys, extra keys, changed placeholders, any digit other than 0 to 9, and any currency sign other than the rupee sign. It exits with 1 if anything is wrong. With no arguments it checks every file except `en.json`.
