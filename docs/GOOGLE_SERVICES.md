# Google services in PayProof

PayProof uses four Google services. Project id: `payproof-nithin-2026`. Cloud Run and Firestore run in `asia-south1`.

## Firebase (Hosting and Authentication)

Firebase Hosting serves the mobile web app from `frontend/` and rewrites `/api/**` to the Cloud Run service `payproof` in `asia-south1`, so the browser talks to one origin. It also sets no-cache headers on HTML, JS and CSS. Firebase Authentication signs each visitor in anonymously from the browser (`frontend/index.html`, project settings in `frontend/firebase-config.js`, a public web configuration that is not a secret). The backend verifies the Firebase ID token on every protected call and takes the user id only from that token (`backend/auth.py`). Hosting configuration: `firebase.json` and `.firebaserc`.

## Firestore

Firestore (native mode, `asia-south1`) holds only confirmed structured data under `users/{uid}`: trips, weeks, costs and answers (`backend/store.py`). It also holds the daily usage counters, updated with atomic transactions, per user and global (`backend/usage_limits.py`), and the shared cache of the curated, simulated sample screenshots in `sample_cache` (`backend/sample_cache.py`). Uploaded images are never written to it. The deployed rules deny all direct client access (`firestore.rules`), so every read and write goes through the backend with its service account. The in-app delete removes a user's data except the usage counters.

## Cloud Run

Cloud Run runs the FastAPI service (`backend/main.py`, built from the `Dockerfile`) as `payproof` in `asia-south1`, with the dedicated `payproof-run` service account, at most 3 instances, 1 GiB and a 60-second timeout. It serves extraction, the pay engine (`engine/`), Q&A (`backend/qa.py`), the evidence pack (`backend/report.py`) and the delete endpoint. Its non-secret settings are in `deploy/env.yaml`; no API key is set because Vertex AI uses the service account. The startup check in `backend/config.py` refuses to start if the Gemini backend is not Vertex AI.

## Gemini on Vertex AI

Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`) on Vertex AI, location `global`, does two jobs: it reads a screenshot into structured data (`extraction/`, one call per screenshot) and it explains results and answers questions through function calling (`backend/qa.py`). It never does arithmetic: every number comes from `engine/`, and the number verifier blocks any other. Every call goes through one small client module, `backend/gemini_client.py`, which switches between Vertex AI (deployed) and AI Studio (local tests with simulated images only). The model has no regional endpoint in `asia-south1`, which is why Vertex AI uses `global`.
