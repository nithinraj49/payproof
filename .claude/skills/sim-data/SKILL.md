---
name: sim-data
description: Generate, refresh or validate the simulated PayProof screenshots and histories. Use when asked to create test data, extend the simulator, check data quality, or prepare the sample screenshots for sample mode.
---

# Simulated data

"Simulate" means we invent trips and weeks, then draw the screens ourselves, so we know the right answer in advance. Follow `REQUIREMENTS.md` section 12.

## Steps

1. Run or extend `eval/generate_data.py`. Layouts: L1 trip detail, L2 trip list, L3 weekly payout (positive); N1 order offer, N2 other screen (negative). Languages: English, `[LANG_1]`, `[LANG_2]`. Include noise variants and variants that omit distance or minutes. Use a fixed seed.
2. Validate: every image has a ground-truth JSON next to it, and each JSON validates against `extraction/schema.py`.
3. Count images per layout, language and noise type and report any empty cell in that grid.
4. **Brand safety:** scan filenames, rendered text and JSON for real platform names (for example Zomato, Swiggy, Uber, Ola, Rapido, Blinkit, Zepto, Dunzo, Porter, Amazon, Flipkart). Any hit is a failure. Confirm no real logos or copied layouts.
5. Open and describe five random images so I can judge whether they look like believable app screens.
6. For sample mode, copy about eight curated images (trip, weekly, one order offer) into `frontend/samples/` with a small index file.
7. Report where fonts came from and their licence.

## Rules

- Value ranges are assumptions for testing; keep them in config, not hard-coded.
- Never use real screenshots here. If a teammate has real ones, they stay private and are never part of accuracy numbers.
- Do not report evaluation numbers from this skill; use `eval-report` for that.
