---
name: demo-rehearsal
description: Rehearse the PayProof demo against the deployed app and time each step. Use before recording the demo video and again on the day of submission.
---

# Demo rehearsal

The video must clearly show the working functionality and be 2:55 to 3:00 long. Read `docs/DEMO.md` for the exact steps.

## Steps

1. Ask me for the deployed Hosting URL and confirm it loads.
2. For each step that has an API call, run it against the deployed app (using the sample images in `frontend/samples/`) and time it with `curl -w "%{time_total}"`. Report the slowest steps.
3. Run the whole demo path three times. Record pass or fail and the total time for each run.
4. List the steps I must check by hand in the browser on a phone (screens, language switch, yellow low-confidence cells, evidence pack download) and give me a checklist.
5. Check the unhappy path shown in the demo: the order-offer screenshot is rejected, an unanswerable question is refused.
6. If the total timing exceeds 3:00, suggest what to trim, starting with the architecture explanation.
7. Remind me: set Cloud Run minimum instances to 1 before recording to avoid a cold start, use a private window, and use sample data only.

## Output

A table: Step, Result, Time. Then a verdict: ready to record, or fix first (list).
