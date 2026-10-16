# Backend-generated user-visible strings

These are produced by the server and are **not** in `en.json`. Line numbers are as of the `live-before-i18n` tag. Text in `{braces}` is filled in by code.

The frontend shows API error `message` fields, engine `data_quality` notes, Q&A answers and extraction `notes` as they arrive. It does not translate them today, so translating them needs a backend change (a later step).

## API error messages (`message` in the error JSON)

| File:line | Code | Text |
|---|---|---|
| backend/auth.py:24 | missing_token | Sign-in required. |
| backend/auth.py:28 | invalid_token | Sign-in session expired or invalid. |
| backend/main.py:65 | unsupported_file_type | Please upload a PNG, JPEG or WebP image. |
| backend/main.py:70 | file_too_large | That image is larger than {max_upload_mb} MB. Please upload a smaller screenshot. |
| backend/main.py:75 | unreadable_image | Could not read that image. Please upload a clear screenshot. |
| backend/main.py:128, 428 | service_busy | PayProof is busy right now. Please try again in a minute. |
| backend/main.py:294, 463 | no_trips | No confirmed trips found. Please upload and confirm trip screenshots first. |
| backend/main.py:368 | no_trips | No confirmed trips found. |
| backend/main.py:321, 473 | no_weeks | No confirmed weekly summaries found. Please upload and confirm a weekly payout screenshot first. |
| backend/main.py:420 | unsupported_language | Only English is supported right now. |
| backend/store.py:173 | costs_not_set | Please enter your fuel and maintenance costs first. |
| backend/usage_limits.py:45 | daily_limit_reached | You've reached today's limit for this. Please try again tomorrow. |
| backend/usage_limits.py:47, 73 | service_busy | PayProof has reached its usage limit for today. Please try again tomorrow. |
| backend/main.py:233, 255, 299, 327, 468, 479 | invalid_data | `str(exc)`: English ValueError text from engine/earnings.py (lines 61, 85, 139, 271, 274), for example "deductions[{i}] must not be negative (got {d})". Technical; the forms should normally prevent these. |

## Image quality rejection (returned as extraction `notes`, backend/main.py:91)

| File:line | Reason | Text |
|---|---|---|
| extraction/image_quality.py:61 | too_small | This image is too small to read. Please retake this screenshot at full size. |
| extraction/image_quality.py:62 | too_blurry | This image looks too blurry to read. Please retake this screenshot in focus. |
| extraction/image_quality.py:63 | low_contrast | This image has too little contrast to read. Please retake this screenshot. |
| extraction/image_quality.py:64 | too_dark | This image is too dark to read. Please retake this screenshot with more light. |
| extraction/image_quality.py:65 | too_bright | This image is too bright/washed out to read. Please retake this screenshot. |

The extraction `notes` field (extraction/schema.py:69) can also hold a short English rejection reason written by Gemini when a screen is not a trip or payout screenshot.

## Data-quality notes (engine, `data_quality` on the Results screen and evidence pack)

| File:line | Text |
|---|---|
| engine/earnings.py:126 | No trips were provided. |
| engine/earnings.py:157-158 | Trip {n}: the amounts add up to {amount}, but its screenshot says {amount}. |
| engine/earnings.py:182 | Total time on trips is zero, so pay per hour on trips is not shown. |
| engine/earnings.py:196 | None of your trips has a distance, so your costs and net earnings cannot be worked out. |
| engine/earnings.py:215 | Hours online is zero, so pay per hour online is not shown. |
| engine/earnings.py:222 | Total distance is zero, so pay per km is not shown. |
| engine/earnings.py:229 | Gross pay is zero, so the deduction share is not shown. |
| engine/earnings.py:300 | Distance driven was not provided, so your costs and net earnings are not shown. |
| engine/earnings.py:310 | Hours online was not provided, so pay per hour online is not shown. |
| engine/earnings.py:312 | Hours online is zero, so pay per hour online is not shown. |
| engine/earnings.py:319 | Distance driven was not provided, so pay per km is not shown. |
| engine/earnings.py:321 | Distance driven is zero, so pay per km is not shown. |
| engine/earnings.py:330 | Gross weekly pay is zero, so the deduction share is not shown. |

Amounts use Indian digit grouping with the rupee sign (engine/earnings.py:39).

## Q&A refusals and fallbacks (backend/qa.py)

| Line | When | Text |
|---|---|---|
| 581-586 | Draft used a number or date not in the stored figures | I can't give a verified answer to this: my draft used a number or date ({list}) that none of your stored figures support. Please check the Results screen for your confirmed numbers. |
| 620-623 | Accusation or legal/financial advice | I can't help with that. I can only explain your own pay numbers from your confirmed data -- I can't say whether a platform did anything wrong, and I can't give legal or financial advice. |
| 624-627 | Wrong currency symbol | I can't give a verified answer to this: amounts here are in Indian rupees (₹), and my draft used a different currency symbol. Please check the Results screen for your confirmed figures. |
| 628-631 | Wrong label for a number | I can't give a verified answer to this: my draft used the wrong label for one of your numbers. Please check the Results screen for your confirmed figures. |
| 638-641 | Empty answer | I couldn't put together an answer to that just now. Please try asking again, or rephrase your question. |

Normal answers are written by Gemini in English from the system prompt (backend/qa.py:205-240), so their wording is not a fixed string. `GLOSSARY` (backend/qa.py:205) holds the plain-language labels for each number. The verifier checks them, so changing a label there also means changing the verifier.

## Evidence pack (backend/report.py, English HTML page)

| Line | Text |
|---|---|
| 152-153 | Heading "PayProof evidence pack"; "Generated by PayProof on {date}. Data source: {source}." |
| 158-159 | Closing notes: "Generated by PayProof. Built only from the screenshots you provided; figures are the worker's own." and "PayProof does not verify your identity or your platform account, and does not contact your platform. It reports what you uploaded and the arithmetic performed on it, nothing more." |
| 166-167 | "Method" heading and the trip-mode method paragraph |
| 171-172 | "Method" heading and the weekly-mode method paragraph |
| 182-191 | Trip row labels (from `GLOSSARY`, with these fallbacks): Trip count, Gross pay, Platform deductions, Net payout, Worker costs, Net earnings, Net pay per engaged hour, Net pay per logged-in hour, Net pay per km, Deduction share |
| 188-190, 237-238 | Units: per hour on trips, per hour online, per km |
| 192-193 | Total distance, Total duration |
| 199, 245, 250 | Fallback labels: Deduction, Earning |
| 205, 256 | Heading: Data-quality notes |
| 219, 269 | Headings: Deductions by type; 268: Earning lines |
| 195-215 | Trip {n}: the amounts add up to {amount}, but the screenshot says {amount} was paid. Followed by: Some trips do not add up to the total payout shown in the screenshot, so figures built from them may be off. |
| 220-224 | Title "PayProof evidence pack (trip mode)"; source "trip mode, 1 confirmed trip / {n} confirmed trips you uploaded or entered" |
| 231-240 | Weekly row labels: Gross weekly pay, Weekly deductions, Total credited, Credited total minus the earning lines, Worker costs, Net earnings, Net pay per online hour, Net pay per km, Deduction share, Net pay per trip hour |
| 259-262 | Your earning lines do not add up to the credited total: net earnings may be understated by about {amount}. |
| 271-274 | Title "PayProof evidence pack (weekly mode)"; source "weekly mode, {period}", fallback period "your most recently confirmed week" |
| 82-123 | "not available" for any missing value; unit formats "{n} km", "{n} min", "{n}%" |

## Other API text

| File:line | Text |
|---|---|
| backend/main.py:363 | Pay-change detection was tested on simulated data and found unreliable, so it is disabled. (feature is off by default) |
| backend/main.py:384 | Not enough trips with confirmed dates to split into periods. |
| engine/changes.py:94-97 | Need at least {n} trips per period with distance data. Got {n} baseline, {n} recent. |
| engine/changes.py:66, 86 | {n} trip(s) excluded because date_confirmed is false / excluded from metric due to missing distance (technical wording) |
| engine/changes.py:110 | Baseline mean is zero — relative change cannot be computed. |
