---
name: eval-report
description: Run the PayProof evaluation scripts and update eval/RESULTS.md with real, unedited numbers. Use when asked to run evaluations, update results, or prepare the benchmark table for the deck or the submission description.
---

# Evaluation report

These numbers go on a public slide and into the submission, so they must be real.

## Steps

1. Make sure the labelled simulated data exists in `eval/data/`. If not, run `eval/generate_data.py` and say how many images and histories were created.
2. Run `eval/run_extraction_eval.py`, `eval/run_change_eval.py`, `eval/run_grounding_eval.py` and the latency script (the latency script needs the deployed URL; ask me for it).
3. Rewrite `eval/RESULTS.md` with the date, the counts of images, histories and questions, and the exact model names, then these tables:
   - extraction accuracy overall and by screen type, language, layout and noise type
   - rejection rate for order-offer and other screens
   - pay-change detection for trip mode and weekly mode: precision, recall, false-alarm rate
   - grounded answers: share whose numbers all come from the engine, and share of correct refusals
   - response time per screenshot and per answer
4. List the top three failure types with two or three concrete examples each.
5. If any number is worse than in the previous `RESULTS.md`, say so at the top.
6. Add a section "Deck slide 11 and submission description" with one line per metric ready to paste, and the character count if you draft sentences for the 1,024-character description.

## Rules

- Never edit a number by hand. Numbers come from script output only.
- Never tune a prompt or add a special case to fit specific test images.
- Say plainly when a result is weak or a sample is small.
