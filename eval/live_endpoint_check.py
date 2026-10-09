"""Live smoke test of the deployed PayProof endpoint, through the real
Firebase Hosting URL (https://payproof-nithin-2026.web.app/api/extract) --
not localhost, not mocked. SIMULATED images only.

Gets a real anonymous Firebase ID token via the Firebase Auth REST API
(identitytoolkit.googleapis.com/v1/accounts:signUp), using the public web API
key from frontend/firebase-config.js (not a secret -- see REQUIREMENTS.md
section 11). The token is held in memory only: never printed, never written
to a file, never logged.

Always prints the call count and cost estimate and waits for --go before
making any request that could call Gemini (REQUIREMENTS.md section 19 rule
9). Two Gemini calls are expected in total: one trip-detail image, one
order-offer image. A repeated upload of the same trip-detail image must be
served from cache with no additional Gemini call.

Usage (PowerShell):
    python -m eval.live_endpoint_check --dry-run
    python -m eval.live_endpoint_check --go
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
FIREBASE_CONFIG_PATH = ROOT / "frontend" / "firebase-config.js"
HOSTING_URL = "https://payproof-nithin-2026.web.app"
EXTRACT_URL = f"{HOSTING_URL}/api/extract"

TRIP_IMAGE = ROOT / "eval" / "generated" / "images" / "L1_002.jpg"
ORDER_OFFER_IMAGE = ROOT / "eval" / "generated" / "images" / "N1_001.jpg"

ESTIMATED_COST_USD = 0.002  # 2 Gemini calls, consistent with earlier live measurements (~$0.0007-0.001/call)


def get_public_api_key() -> str:
    text = FIREBASE_CONFIG_PATH.read_text()
    match = re.search(r'apiKey:\s*"([^"]+)"', text)
    if not match:
        raise SystemExit(f"Could not find apiKey in {FIREBASE_CONFIG_PATH}")
    return match.group(1)


def get_anonymous_id_token(api_key: str) -> str:
    """Firebase Auth REST API, accounts:signUp with no email/password = a new
    anonymous user. Returns the idToken only; never printed or saved."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={api_key}"
    response = httpx.post(url, json={"returnSecureToken": True}, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["idToken"]  # caller must not print this


def run_checks(token: str) -> list:
    """Returns a list of (check_name, passed, detail) tuples. detail never
    includes the token."""
    results = []
    headers = {"Authorization": f"Bearer {token}"}

    # (a) trip-detail image: expect 200 and a valid ExtractionResult
    trip_bytes = TRIP_IMAGE.read_bytes()
    r = httpx.post(EXTRACT_URL, headers=headers,
                    files={"file": ("trip.jpg", trip_bytes, "image/jpeg")}, timeout=60)
    ok = r.status_code == 200
    body = r.json() if ok else r.text
    if ok:
        ok = body.get("screen_type") == "trip_detail" and bool(body.get("trips"))
    results.append(("(a) trip-detail image -> 200 + valid ExtractionResult", ok,
                     f"status={r.status_code} screen_type={body.get('screen_type') if isinstance(body, dict) else body}"))

    # (b) same image again: expect identical result, served from cache (no new Gemini call --
    # verified afterward from the logs, not here)
    r2 = httpx.post(EXTRACT_URL, headers=headers,
                     files={"file": ("trip.jpg", trip_bytes, "image/jpeg")}, timeout=60)
    ok2 = r2.status_code == 200 and r2.json() == body
    results.append(("(b) same image again -> identical cached result", ok2,
                     f"status={r2.status_code} identical={r2.json() == body if r2.status_code == 200 else 'n/a'}"))

    # (c) order-offer image: expect rejection, no trip/payout numbers
    offer_bytes = ORDER_OFFER_IMAGE.read_bytes()
    r3 = httpx.post(EXTRACT_URL, headers=headers,
                     files={"file": ("offer.jpg", offer_bytes, "image/jpeg")}, timeout=60)
    ok3 = r3.status_code == 200
    body3 = r3.json() if ok3 else r3.text
    if ok3:
        ok3 = body3.get("screen_type") == "order_offer" and not body3.get("trips") and body3.get("payout_summary") is None
    results.append(("(c) order-offer image -> rejected, no numbers", ok3,
                     f"status={r3.status_code} screen_type={body3.get('screen_type') if isinstance(body3, dict) else body3}"))

    # (d) no token: expect 401
    r4 = httpx.post(EXTRACT_URL, files={"file": ("trip.jpg", trip_bytes, "image/jpeg")}, timeout=30)
    ok4 = r4.status_code == 401
    results.append(("(d) no token -> 401", ok4, f"status={r4.status_code}"))

    # (e) oversized file: expect a friendly error (413), not a 500
    oversized = b"\x00" * (9 * 1024 * 1024)  # 9 MB > MAX_UPLOAD_MB=8
    r5 = httpx.post(EXTRACT_URL, headers=headers,
                     files={"file": ("big.png", oversized, "image/png")}, timeout=60)
    ok5 = r5.status_code == 413
    results.append(("(e1) oversized file -> 413, not 500", ok5, f"status={r5.status_code}"))

    # (e) wrong file type: expect a friendly error (415), not a 500
    r6 = httpx.post(EXTRACT_URL, headers=headers,
                     files={"file": ("note.txt", b"not an image", "text/plain")}, timeout=30)
    ok6 = r6.status_code == 415
    results.append(("(e2) wrong file type -> 415, not 500", ok6, f"status={r6.status_code}"))

    return results


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--go", action="store_true")
    args = parser.parse_args()

    print(f"Live endpoint: {EXTRACT_URL}")
    print(f"Images: {TRIP_IMAGE.name} (trip-detail), {ORDER_OFFER_IMAGE.name} (order-offer) -- both simulated")
    print("Gemini calls planned: 2 (one per distinct image; the repeated trip-detail upload must hit the cache)")
    print(f"Estimated cost: ~${ESTIMATED_COST_USD}")
    print("Checks: (a) trip image, (b) repeat trip image (cached), (c) order-offer rejection, "
          "(d) no token -> 401, (e1) oversized -> 413, (e2) wrong type -> 415")

    if args.dry_run:
        print("\n--dry-run: no live request made. Re-run with --go after the owner says \"go\".")
        return

    print("\nOwner said \"go\". Getting an anonymous Firebase ID token...")
    api_key = get_public_api_key()
    token = get_anonymous_id_token(api_key)
    print("Got token (not printed, not saved).")

    print("\nRunning checks against the live endpoint...")
    results = run_checks(token)
    del token  # best-effort: drop the only reference once we're done with it

    print("\n=== Results ===")
    print(f"{'Check':<55} {'Result':<6} Detail")
    all_passed = True
    for name, passed, detail in results:
        all_passed &= passed
        print(f"{name:<55} {'PASS' if passed else 'FAIL':<6} {detail}")

    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
