# PayProof demo script (video, at most 2:50)

Sample mode only. Everything on screen is simulated: a fictional platform, generated screenshots, no real worker's data. Planned running time **2:46**, which leaves 4 seconds of slack.

## Before you press record

- Open a **new private/incognito window** at `https://payproof-nithin-2026.web.app`. Use a new private window for every take: the opening splash plays once per browser session, and a fresh window also means a fresh anonymous user with nothing saved.
- Size the window like a phone (about 390 px wide) or record on a phone. Browser zoom 100%.
- Close every other tab, turn off notifications, hide the bookmarks bar.
- **Start screen:** the opening splash (four animated bars), which then slides up to the first screen with the headline "Know what you really earn."
- Do one silent rehearsal first. The three sample screenshots are cached on the server, so sample extraction is instant and costs nothing.
- Rehearse the Check screen once: on the trip sample the **Incentive** and **Tip** cells are blank ("Not readable from your screenshot - type the value from your screenshot"), and typing a value confirms that cell. If your build shows them already confirmed, skip those two typing steps.

## Steps, timings and what to say

| Time | Screen and action | Say (one sentence) |
|---|---|---|
| 0:00-0:12 | **Splash**, then the first screen. Let the bars finish; do not tap. | "Gig workers see what a platform pays them, not what they really earn after fuel and wear, and PayProof works that out from screenshots they already have." |
| 0:12-0:26 | Tap **Try with sample screenshots**. Point at the "simulated examples from a fictional app" note. On **Trip screenshot** tap **Use this sample**. | "These are simulated screenshots from a fictional app, so no real worker's data is shown." |
| 0:26-0:56 | **Check screen** (the screenshot sits beside the table). In **Incentive** type **0**. In **Tip** type **10** (the mismatch take). Tap **Confirm date**, then **Confirm and continue**. The warning appears: "These amounts add up to ₹146.65, but your screenshot says ₹136.65 was paid. Check the incentive, tip and deductions." Tap **Fix the numbers**, change **Tip** to **0**, tap **Confirm and continue**. | "Gemini only reads the screenshot and I check every number against it; if the amounts do not add up to the screenshot's own total, PayProof warns me before anything is saved." |
| 0:56-1:08 | **Costs screen.** Values are prefilled (fuel 3, maintenance 1, hours online 1.5). Tap **Save costs**. | "I enter my own costs per kilometre and my hours online, and nothing is guessed." |
| 1:08-1:28 | **Results** ("Your real pay"). Pause on net earnings **₹98.65** and the two cards **₹190.94 per hour on trips** and **₹65.77 per hour online**. Scroll to **₹14.38 per km** and the **Where your money went** chart. | "Per hour on trips only counts time driving and per hour online also counts waiting, and every figure comes from fixed formulas, never from the AI." |
| 1:28-1:50 | Tap **Ask**. Tap the chip **What was my net pay per hour?** and show the **Verified** badge and the ₹ answer. Then type **Is the platform cheating me?** and tap **Ask** (show the plain refusal). | "Every number in an answer is checked against my own data, and PayProof will not accuse anyone, it plainly declines." |
| 1:50-2:00 | Tap **Home**. Tap **Try with sample screenshots**, then **Use this sample** on **Order offer (should be rejected)**. Show "We couldn't use this screenshot". | "An order offer is a promise, not a payout, so PayProof rejects it and shows no numbers." |
| 2:00-2:22 | Tap **Home** (or **Try another screenshot**), **Try with sample screenshots**, **Use this sample** on **Weekly payout screenshot**. Tap **Confirm and continue**, then **Save costs**. Show **₹7,949.58** net, **₹189.28 per hour online**, **₹30.50 per km** and the note that per-trip hours are not available in weekly mode. | "A weekly payout works too, and PayProof says honestly that it cannot give a per-trip rate from it." |
| 2:22-2:32 | Tap **Evidence & delete**, then **Open evidence pack**. Show the top of the page for 3 seconds. Close that tab without printing. | "I also get a plain evidence pack I can show anyone, built only from what I confirmed." |
| 2:32-2:46 | Back on **Evidence & delete**, tap **Delete all my data**, then **Yes, delete everything**. Show "Your data has been deleted." | "One tap deletes everything PayProof stored for me." |

**If you run long, cut in this order:** the order-offer step (10 s), then the evidence-pack step (10 s), then the enlarge-the-screenshot tap if you used it. Do not cut the mismatch warning, the Verified answer or the delete.

## Exact start and end screens

- **Start:** the opening splash on a fresh private window, then the first screen.
- **End:** the confirmation "Your data has been deleted." Hold on it for 2 seconds.

## What to avoid showing

- **Real platform screenshots, logos or marketing images.** Use only the three built-in samples, which are labelled simulated.
- **Keys and secrets.** No `.env`, no `frontend/firebase-config.js`, no Firebase or Google Cloud console, no token or API key in the address bar.
- **Terminals, code editors and browser developer tools**, including the Network tab.
- **The red technical error line** at the bottom of the screen. If it appears, stop, open a new private window and retake.
- **An address bar with `?nosplash=1`** (it skips the opening splash) or any `#` fragment other than the plain site address.
- **Another person's data.** Use a fresh private window for every take.
- **Printing the evidence pack.** Open it, glance at it, close the tab.
- **Words the app does not use.** Do not say "proof", "cheating", "fraud" or "caught" about a platform. Say "does not add up", "may be off" or "possible change". The pay-change signal is disabled and is not shown.

## Figures quoted in this script (computed by the engine, not by hand)

| Sample | Net earnings | Per hour | Per km |
|---|---|---|---|
| Trip: base ₹136.65, 9.5 km, 31 min, fuel 3 + maintenance 1 per km, 1.5 hours online | ₹98.65 | ₹190.94 on trips, ₹65.77 online | ₹14.38 |
| Weekly: ₹5,257.63 + ₹3,891.95 = ₹9,149.58, 300 km, 42 hours, fuel 3 + maintenance 1 | ₹7,949.58 | ₹189.28 online (per-trip hour not available) | ₹30.50 |
| Mismatch take: the trip sample with a typed Tip of ₹10 | warning: the amounts add up to ₹146.65, the screenshot says ₹136.65 | | |
