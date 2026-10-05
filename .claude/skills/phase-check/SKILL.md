---
name: phase-check
description: Review the current PayProof build phase against its acceptance criteria before committing, merging or tagging. Use at the end of every phase or pull request, or when asked to check progress, review the phase or prepare a commit.
---

# Phase check

Report facts only. If you cannot check something, write "cannot check" instead of guessing.

## Steps

1. Read `ROADMAP.md` and find the current phase and the track I am working on. If unclear, ask once.
2. Run `pytest -q`. Report passed and failed counts and name any failing test.
3. Run `git status` and `git diff --stat`. Flag uncommitted work, very large changes, and any file edited outside my track's folders (see the track table in `CLAUDE.md`).
4. Secrets scan of tracked and staged files: private keys, service-account JSON, `.env` files, API-key-like strings (for example text starting with `AIza`). Confirm `.env` is in `.gitignore`.
5. Check the Hard rules in `CLAUDE.md`:
   - no LLM or network call anywhere in `engine/`
   - uploaded images are never written to disk, storage or logs
   - names, phone numbers and addresses are never extracted or stored
   - demos, tests and samples use fictional platforms only, with no copied real designs
   - no code or files copied from earlier projects (ask me if unsure)
   - wording is "possible change" or "no clear change", never "cheating", "fraud" or "proof"
6. Compare the phase's acceptance criteria and "You verify" items in `ROADMAP.md`, and any related scenarios in `REQUIREMENTS.md` section 16, one by one. Mark each Met, Not met, or Cannot check.
7. Update `PROGRESS.md`: done, next, open questions.
8. Propose a commit message and a tag name. Do NOT commit, tag, push or merge without asking me.

## Output

A table with columns Check, Result, Evidence, then a one-line verdict: ready to merge, or blocked by (list).
