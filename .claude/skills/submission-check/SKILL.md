---
name: submission-check
description: Final pre-submission check for the Google Cloud AI Builder Cup form. Use on 16 or 17 Oct, or whenever asked whether the submission is ready.
---

# Submission check

Report facts only. For anything you cannot verify yourself, ask me to confirm and mark it "Needs you".

## The form items

1. **Challenge** chosen: ask me which one.
2. **Prototype link** (the Firebase Hosting URL): `curl` it and report the status code; ask me to confirm it works on a phone in a private window and that the sample button completes the flow.
3. **Deck PDF**: find the file, report its size with `ls -l` (limit 5 MB), and ask me to confirm it uses the official template.
4. **GitHub repository**: confirm the remote with `git remote -v`; use `gh repo view --json visibility` if the `gh` CLI is available, otherwise ask me to confirm it is public.
5. **Demo video link**: ask me for the link and to confirm the length is 3 minutes or less and that it clearly shows the working flow. (The form field says up to 3 minutes and the rules text says 3 to 4; 2:55 to 3:00 satisfies both.)
6. **Description**: count characters in `docs/submission_description.md` with `wc -m` (limit 1,024), and check that it names Firebase, Firestore, Cloud Run and Gemini.

## Repo hygiene

- Scan the full git history for secrets (keys, `.env`, service-account JSON).
- Confirm the README has the architecture, the evaluation results and the limits.
- Confirm `eval/RESULTS.md` matches the numbers on deck slide 11 and in the description.

## Evaluation readiness

- The live app must stay up from 19 Oct to 6 Nov and until the Top 50 announcement on 7 Nov. Check minimum instances, the uptime check, the billing alert and remaining credits.

## Output

A table: Item, Status (OK, Problem, Needs you), Detail. Do not submit anything.
