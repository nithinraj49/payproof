---
name: deploy-check
description: Deploy PayProof to Cloud Run and Firebase Hosting, then run smoke tests. Use only when I ask to deploy, redeploy, or check that the live app works.
---

# Deploy and smoke test

## Before deploying

1. Show me the project id, region and model names from the environment. Never print secrets.
2. Run `pytest -q`. If tests fail, stop and report.
3. Ask me to confirm before any deploy command. Never deploy on your own, and only deploy from `main`.

## Deploy

1. Backend: `gcloud run deploy payproof --source . --region $REGION --allow-unauthenticated --env-vars-file=deploy/env.yaml` (plus `--service-account`, `--max-instances=3`, `--memory`, `--timeout` as already agreed). Always use `--env-vars-file=deploy/env.yaml`, never a raw `--set-env-vars` list — a comma-separated `--set-env-vars` value was silently mangled by PowerShell/gcloud on Windows once already (only the first variable survived, with a garbled value), and it went undetected until the environment variables were dumped and checked individually. `--env-vars-file` **replaces every existing environment variable** on the service, which is also the fix for any stale/garbled value from a previous deploy. Note the previous revision name for rollback.
2. Front end: `firebase deploy --only hosting`.

## Smoke tests

1. `curl -s -o /dev/null -w "%{http_code}" <cloud-run-url>/health` should return 200.
2. The Firebase Hosting URL should load the page.
3. `curl` `<hosting-url>/api/whoami` without a token: expect 401. That proves the Hosting rewrite reaches Cloud Run and that auth is enforced.
4. **Compare live environment variables against `deploy/env.yaml`, one by one.** Run `gcloud run services describe payproof --region asia-south1 --project payproof-nithin-2026 --format="yaml(spec.template.spec.containers[0].env)"` and show a table: variable, expected (from `deploy/env.yaml`), live, match yes/no. Confirm there is no `GEMINI_API_KEY` on the service. Do not trust `/health` and `/api/whoami` passing as proof the environment variables are correct — they don't touch Gemini config and can pass even when the rest of the environment is broken.
5. Print the live URLs and remind me to test on a phone over mobile data, in a private window, using the sample button.

## Reminders

- The app must stay live through the evaluation period (until at least 7 Nov). Check the billing alert, minimum instances and the uptime check.
- Rollback: if something breaks, tell me how to send traffic back to the previous revision (`gcloud run services update-traffic`) and ask before doing it.
