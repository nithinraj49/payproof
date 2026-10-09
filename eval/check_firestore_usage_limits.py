"""Manual check that backend/usage_limits.py's atomic Firestore counters work
against the REAL project (payproof-nithin-2026) -- not mocked, not an
emulator. The Firestore emulator cannot run in the Claude Code sandbox used
to build this (no Java: `firebase emulators:start` fails with "Could not
spawn `java -version`"), so this check exists for the owner to run by hand.

It is NOT part of `pytest -q` and never runs automatically. It uses the real
check_and_increment() function from backend/usage_limits.py (not a
reimplementation), against obviously-fake uid and day values
("_throwaway_check_uid", "throwaway-test-<timestamp>") that can never collide
with a real user or a real day's counters, then deletes every document it
created. If this script is interrupted before cleanup, the leftover
documents are easy to find and remove by hand (see the printed paths).

Usage (PowerShell), from the repo root, with your own gcloud credentials:
    python -m eval.check_firestore_usage_limits
"""
import datetime
import sys

from backend.usage_limits import check_and_increment, get_db
from backend.errors import ApiError

TEST_UID = "_throwaway_check_uid"
TEST_DAY = f"throwaway-test-{datetime.datetime.now().strftime('%Y%m%dT%H%M%S')}"


def main():
    db = get_db()
    user_ref = db.collection("users").document(TEST_UID).collection("usage").document(TEST_DAY)
    global_ref = db.collection("usage_global").document(TEST_DAY)

    print(f"Project: {db.project}")
    print(f"Throwaway document paths (will be deleted at the end):")
    print(f"  users/{TEST_UID}/usage/{TEST_DAY}")
    print(f"  usage_global/{TEST_DAY}")
    print()

    failures = []
    try:
        print("1. First call with limit=2: should succeed, counts become 1.")
        check_and_increment(TEST_UID, "extractions", user_limit=2, global_limit=2, db=db, day=TEST_DAY)
        user_doc = user_ref.get()
        global_doc = global_ref.get()
        print(f"   users doc: {user_doc.to_dict()}")
        print(f"   global doc: {global_doc.to_dict()}")
        if user_doc.to_dict().get("extractions") != 1 or global_doc.to_dict().get("gemini_calls") != 1:
            failures.append("counts after first call were not both 1")

        print("\n2. Second call with the same limit=2: should succeed, counts become 2.")
        check_and_increment(TEST_UID, "extractions", user_limit=2, global_limit=2, db=db, day=TEST_DAY)
        user_doc = user_ref.get()
        if user_doc.to_dict().get("extractions") != 2:
            failures.append("count after second call was not 2")
        print(f"   users doc: {user_doc.to_dict()}")

        print("\n3. Third call with the same limit=2: should raise ApiError 429 (user limit reached).")
        try:
            check_and_increment(TEST_UID, "extractions", user_limit=2, global_limit=99, db=db, day=TEST_DAY)
            failures.append("third call did not raise (user limit should have blocked it)")
        except ApiError as exc:
            print(f"   Raised as expected: {exc.status_code} {exc.error_code}")
            if exc.status_code != 429:
                failures.append(f"expected status 429, got {exc.status_code}")

        print("\n4. Call with global_limit already reached (global_limit=2, count is already 2): should raise ApiError 503.")
        try:
            check_and_increment(TEST_UID + "_other", "extractions", user_limit=99, global_limit=2, db=db, day=TEST_DAY)
            failures.append("fourth call did not raise (global limit should have blocked it)")
        except ApiError as exc:
            print(f"   Raised as expected: {exc.status_code} {exc.error_code}")
            if exc.status_code != 503:
                failures.append(f"expected status 503, got {exc.status_code}")

    finally:
        print("\nCleaning up throwaway documents...")
        user_ref.delete()
        global_ref.delete()
        still_there = user_ref.get().exists or global_ref.get().exists
        if still_there:
            print("!!! WARNING: at least one throwaway document still exists after delete. Remove it by hand:")
            print(f"    users/{TEST_UID}/usage/{TEST_DAY}")
            print(f"    usage_global/{TEST_DAY}")
            failures.append("cleanup did not fully delete the throwaway documents")
        else:
            print("Confirmed deleted.")

    print()
    if failures:
        print(f"FAILED ({len(failures)} problem(s)):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("PASSED: the real Firestore transaction behaves as backend/usage_limits.py expects.")


if __name__ == "__main__":
    main()
