// Dev-only test harness (not deployed; see run.mjs): serves frontend/ with Firebase swapped for
// stubs and a stub /api, so the real app code can be driven in headless Edge with no
// network and no Gemini/Firebase calls.
import http from "http";
import { readFileSync, existsSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const FRONTEND = process.env.FRONTEND_DIR ? path.resolve(process.env.FRONTEND_DIR) : path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend"); // FRONTEND_DIR: test another copy of frontend/ (e.g. an older tag)
export const counters = { ask: 0, askBodies: [], extract: 0, other: {} };
// extractType: null | "other" (model says not a trip or payout screen) | "quality" (image-quality gate) | "err415" | "err400"
// summaryError: null | { status, code }.  weeklyGap: the weekly reconciliation panel and Results note appear.
export const modes = { reconDynamic: false, reconFlag: false, extractType: null, summaryError: null, weeklyGap: false };
export const BACKEND_ENGLISH = [
  "This is an incoming order offer, not a completed trip.",
  "This is a welcome or informational screen, not an earnings screen.",
  "This image looks too blurry to read. Please retake this screenshot in focus.",
  "Please upload a PNG, JPEG or WebP image.",
  "BACKEND ENGLISH MESSAGE",
  "Your net pay per hour was ₹195.58.",
  "Weekly screenshots do not show trip minutes.",
  "Trip 1: the amounts add up to ₹147.02, but its screenshot says ₹136.65.",
  "Distance driven was not provided, so pay per km is not shown.", "Food delivery", "SIM-1001", "Platform fee", "Trip earnings", "Incentives", "5 Oct to 11 Oct 2026",
]; // texts the stubs return, i.e. what the real backend or extraction would put on screen in English

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml" };

const stubAuth = `export function getAuth(){return {currentUser:{getIdToken:async()=>"stub"}}}
export function signInAnonymously(){return Promise.resolve({})}
export function onAuthStateChanged(a,cb){setTimeout(()=>cb({uid:"stub"}),0)}`;
const stubApp = `export function initializeApp(){return {}}`;

const tripExtract = {
  screen_type: "trip_detail", currency: "INR", needs_review: false, notes: null,
  trips: [{ order_id: "SIM-1001", order_type: "Food delivery", trip_date: "2026-10-08", base_pay: 120, incentive: 20, tip: 0,
    total_payout: 130, distance_km: 6.5, duration_min: 28, deductions: [{ label: "Platform fee", amount: 10 }], low_confidence_fields: [] }],
};
const weeklyExtract = {
  screen_type: "payout_summary", currency: "INR", needs_review: false, notes: null,
  payout_summary: { period_label: "5 Oct to 11 Oct 2026", credited_on: "2026-10-12", lines: [{ label: "Trip earnings", amount: 8000 }, { label: "Incentives", amount: 500 }],
    deductions: [{ label: "Platform fee", amount: 300 }], total_credited: 8200, low_confidence_fields: [] },
};
const offerExtract = { screen_type: "order_offer", currency: "INR", needs_review: false, notes: "This is an incoming order offer, not a completed trip.", trips: [] };
const tripSummary = { mode: "trip", gross_pay: 1200.5, platform_deductions: 100, worker_costs: 260, net_earnings: 7823, net_per_engaged_hour: 195.58, net_per_logged_in_hour: 147.02,
  net_payout_per_km: 30.08, deduction_share: 0.0588, reconciliation_flagged_trips: 2, data_quality: ["Trip 1: the amounts add up to ₹147.02, but its screenshot says ₹136.65."] };
const weeklySummary = { mode: "weekly", gross_weekly: 8500, deductions_weekly: 300, worker_costs_weekly: 250, net_earnings_weekly: 7949.58, net_per_online_hour: 189.28,
  per_hour_on_trips_unavailable: "Weekly screenshots do not show trip minutes.", net_payout_per_km: 30.5, deduction_share: 0, reconciliation_gap: 0, data_quality: [] };

function readBody(req) {
  return new Promise((resolve) => { const chunks = []; req.on("data", (c) => chunks.push(c)); req.on("end", () => resolve(Buffer.concat(chunks))); });
}

export function startServer(port = 0) {
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    const send = (code, body, type = "application/json") => { res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store" }); res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body)); };
    if (url.pathname === "/__stub_auth.js") return send(200, stubAuth, "text/javascript");
    if (url.pathname === "/__stub_app.js") return send(200, stubApp, "text/javascript");
    if (url.pathname.startsWith("/api/")) {
      const body = (await readBody(req)).toString("latin1");
      const name = url.pathname + " " + req.method;
      counters.other[name] = (counters.other[name] || 0) + 1;
      if (url.pathname === "/api/extract") {
        counters.extract += 1;
        counters.lastIsSample = (/name="is_sample"\s+(true|false)/.exec(body) || [])[1];
        counters.lastFile = (/filename="([^"]+)"/.exec(body) || [])[1];
        if (modes.extractType === "other") return send(200, { screen_type: "other", currency: "INR", needs_review: false, trips: [], notes: "This is a welcome or informational screen, not an earnings screen." });
        if (modes.extractType === "quality") return send(200, { screen_type: "other", needs_review: true, trips: [], payout_summary: null, notes: "This image looks too blurry to read. Please retake this screenshot in focus." });
        if (modes.extractType === "err415") return send(415, { error_code: "unsupported_file_type", message: "Please upload a PNG, JPEG or WebP image." });
        if (modes.extractType === "err400") return send(400, { error_code: "unreadable_image", message: "Could not read that image. Please upload a clear screenshot." });
        if (/sample-(?:[a-z]{2}-)?weekly/.test(body)) return send(200, weeklyExtract);
        if (/order[-_]offer/.test(body)) return send(200, offerExtract);
        return send(200, tripExtract);
      }
      if (url.pathname === "/api/trip-reconciliation") {
        if (modes.reconDynamic) { // the engine's check, mimicked: base + incentive + tip - deductions against the total, tolerance 0.5
          const flagged = [];
          (JSON.parse(body).trips || []).forEach((t, trip_index) => {
            const computed = t.base_pay + t.incentive + t.tip - (t.deductions || []).reduce((n, d) => n + d.amount, 0);
            if (Math.abs(computed - t.total_payout) > 0.5) flagged.push({ trip_index, computed_total: computed, total_payout: t.total_payout, gap: computed - t.total_payout });
          });
          return send(200, { flagged_count: flagged.length, flagged });
        }
        return send(200, modes.reconFlag ? { flagged_count: 1, flagged: [{ computed_total: 147.02, total_payout: 136.65 }] } : { flagged_count: 0, flagged: [] });
      }
      if (url.pathname === "/api/weekly-reconciliation") return send(200, modes.weeklyGap ? { reconciliation_gap: 200, net_payout_weekly: 8000, total_credited: 8200 } : { reconciliation_gap: 0, net_payout_weekly: 8200, total_credited: 8200 });
      if (url.pathname === "/api/summary") {
        if (modes.summaryError) return send(modes.summaryError.status, { error_code: modes.summaryError.code, message: "BACKEND ENGLISH MESSAGE" });
        const weekly = url.searchParams.get("mode") === "weekly";
        return send(200, weekly ? { ...weeklySummary, reconciliation_gap: modes.weeklyGap ? 200 : 0, data_quality: modes.weeklyGap ? ["Distance driven was not provided, so pay per km is not shown."] : [] } : tripSummary);
      }
      if (url.pathname === "/api/ask") { counters.ask += 1; counters.askBodies.push(body); return send(200, { verified: true, text: "Your net pay per hour was ₹195.58." }); }
      if (url.pathname === "/api/report") return send(200, "<p>report</p>", "text/html");
      if (url.pathname.startsWith("/api/err/")) {
        const [, , , status, code] = url.pathname.split("/");
        return send(Number(status), { error_code: code, message: "BACKEND ENGLISH MESSAGE" });
      }
      return send(200, {});
    }
    let file = path.join(FRONTEND, url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname));
    if (!file.startsWith(FRONTEND) || !existsSync(file)) return send(404, "not found", "text/plain");
    let data = readFileSync(file);
    const ext = path.extname(file);
    if (ext === ".js" || ext === ".html") {
      data = data.toString("utf8")
        .replace(/https:\/\/www\.gstatic\.com\/firebasejs\/[\d.]+\/firebase-auth\.js/g, "/__stub_auth.js")
        .replace(/https:\/\/www\.gstatic\.com\/firebasejs\/[\d.]+\/firebase-app\.js/g, "/__stub_app.js");
    }
    send(200, data, TYPES[ext] || "application/octet-stream");
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve({ server, port: server.address().port })));
}
