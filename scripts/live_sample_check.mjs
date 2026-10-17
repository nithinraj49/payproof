#!/usr/bin/env node
// Dev-only (not deployed). Sends the language sample images through the LIVE /api/extract
// (normal upload, no is_sample flag) and compares every extracted field with the numbers drawn
// on the image. Each call costs real money (one Gemini call, about $0.001), so:
//   * a counter file in the temp folder caps the TOTAL number of live calls at 20, across runs;
//   * at most 8 calls per throwaway anonymous user (the daily limit is 12 per user);
//   * every throwaway user's data is deleted through DELETE /api/data at the end.
// usage: node scripts/live_sample_check.mjs --go <lang/kind> [<lang/kind> ...]   e.g. hi/trip hi/weekly ta/order_offer
import { readFileSync, writeFileSync, existsSync } from "fs";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASE = process.env.BASE || "https://payproof-nithin-2026.web.app";
const CAP = 20, PER_USER = 8;
const counterFile = path.join(os.tmpdir(), "payproof-live-sample-calls.json");
const counter = existsSync(counterFile) ? JSON.parse(readFileSync(counterFile, "utf8")) : { calls: 0, log: [] };

const args = process.argv.slice(2);
if (!args.includes("--go")) { console.log("Dry run. Add --go to make live calls. Calls used so far:", counter.calls, "of", CAP); process.exit(0); }
const jobs = args.filter((a) => a !== "--go");
if (counter.calls + jobs.length > CAP) { console.log(`REFUSED: ${counter.calls} calls used + ${jobs.length} requested > cap ${CAP}`); process.exit(2); }
console.log(`Plan: ${jobs.length} live extraction call(s) (${counter.calls} used so far, cap ${CAP}), about $${(jobs.length * 0.001).toFixed(3)}.`);

const apiKey = readFileSync(path.join(root, "frontend", "firebase-config.js"), "utf8").match(/apiKey:\s*"([^"]+)"/)[1]; // public web key, not a secret

async function newUser() {
  const r = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=${apiKey}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ returnSecureToken: true }) });
  const j = await r.json();
  if (!j.idToken) throw new Error("anonymous sign-in failed: " + JSON.stringify(j).slice(0, 200));
  return { token: j.idToken, used: 0 };
}

const near = (a, b) => typeof a === "number" && Math.abs(a - b) < 0.005;
const has = (arr, v) => (arr || []).some((x) => near(Math.abs(Number(x.amount)), v));

function scoreTrip(r) {
  const t = (r.trips || [])[0] || {};
  const ded = (t.deductions || []).reduce((s, d) => s + Math.abs(Number(d.amount) || 0), 0);
  const checks = {
    screen_type: r.screen_type === "trip_detail" || r.screen_type === "trip_list",
    order_id: t.order_id === "TR-90417",
    trip_date: t.trip_date === "2026-10-08",
    base_pay: near(t.base_pay, 72.5), incentive: near(t.incentive, 15), tip: near(t.tip, 20),
    deductions: near(ded, 9.4), total_payout: near(t.total_payout, 98.1),
    distance_km: near(t.distance_km, 6.8), duration_min: near(t.duration_min, 31),
  };
  return checks;
}
function scoreWeekly(r) {
  const p = r.payout_summary || {};
  const label = String(p.period_label || "");
  return {
    screen_type: r.screen_type === "payout_summary",
    period_label: /(^|\D)0?5(\D|$)/.test(label) && /11/.test(label) && /2026/.test(label),
    credited_on: p.credited_on === "2026-10-13",
    line_6420: has(p.lines, 6420), line_1150: has(p.lines, 1150), line_380: has(p.lines, 380),
    ded_410: has(p.deductions, 410), ded_120: has(p.deductions, 120),
    total_credited: near(p.total_credited, 7420),
  };
}
function scoreOffer(r) {
  const noNumbers = (!r.trips || r.trips.length === 0) && !r.payout_summary;
  return { rejected_as_order_offer: r.screen_type === "order_offer" && noNumbers };
}

const users = [];
let user = null;
const results = [];
for (const job of jobs) {
  const [lang, kind] = job.split("/");
  const file = path.join(root, "frontend", "samples", lang, `${kind}.png`);
  if (!user || user.used >= PER_USER) { user = await newUser(); users.push(user); }
  const form = new FormData();
  form.append("file", new Blob([readFileSync(file)], { type: "image/png" }), `sample-${lang}-${kind}.png`);
  form.append("is_sample", "false");
  counter.calls += 1; user.used += 1;
  counter.log.push({ job, at: new Date().toISOString() });
  writeFileSync(counterFile, JSON.stringify(counter)); // count BEFORE the call, so a crash never hides a call
  const r = await fetch(`${BASE}/api/extract`, { method: "POST", headers: { Authorization: `Bearer ${user.token}` }, body: form });
  const body = await r.json().catch(() => ({}));
  const checks = r.ok ? (kind === "trip" ? scoreTrip(body) : kind === "weekly" ? scoreWeekly(body) : scoreOffer(body)) : { http: false };
  const wrong = Object.entries(checks).filter(([, ok]) => !ok).map(([k]) => k);
  results.push({ lang, kind, status: r.status, total: Object.keys(checks).length, right: Object.keys(checks).length - wrong.length, wrong, screen_type: body.screen_type, needs_review: body.needs_review, notes: body.notes, extracted: body });
  console.log(`${lang.padEnd(2)} ${kind.padEnd(11)} HTTP ${r.status} ${Object.keys(checks).length - wrong.length}/${Object.keys(checks).length} ${wrong.length ? "WRONG/BLANK: " + wrong.join(",") : "ok"} (screen_type=${body.screen_type}${body.needs_review ? ", needs_review" : ""})`);
}

for (const u of users) {
  const d = await fetch(`${BASE}/api/data`, { method: "DELETE", headers: { Authorization: `Bearer ${u.token}` } });
  console.log("delete throwaway user's data:", d.status);
}
writeFileSync(path.join(os.tmpdir(), `payproof-live-sample-results-${Date.now()}.json`), JSON.stringify(results, null, 1));
console.log(`Live calls used in total: ${counter.calls} of ${CAP}.`);
