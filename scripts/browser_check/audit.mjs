// Dev-only (not deployed). Two checks over EVERY screen and state, with the stubbed API (no Gemini, no network):
//   node scripts/browser_check/audit.mjs --switch [pairs]   language-switch test: render in language A, switch to B, fail on
//                                                           any text left over from A (default pairs: en>ta ta>en hi>ml ml>hi te>kn kn>te)
//   node scripts/browser_check/audit.mjs --audit [langs]    English-leak audit: every visible text node, placeholder, aria-label, title
//                                                           and alt in the five non-English languages is classified as allowed / backend
//                                                           text or data / missing key / hard-coded; exit 1 if anything is "missing key"
//                                                           or "hard-coded". The table is printed and saved to the temp folder.
// env: EDGE=<path to msedge.exe or chrome.exe>, WIDTH=360. One output line per check; a browser call with no answer for 60 s is a
// failure and the browser is restarted.
import { spawn, spawnSync } from "child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "fs";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";
import { startServer, modes, counters, BACKEND_ENGLISH } from "./harness_server.mjs";
import { INIT_SOURCE } from "./init_script.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const LANG_DIR = path.join(here, "..", "..", "frontend", "lang");
const dict = {};
for (const l of ["en", "hi", "ta", "te", "kn", "ml"]) dict[l] = JSON.parse(readFileSync(path.join(LANG_DIR, `${l}.json`), "utf8"));

const args = process.argv.slice(2);
const MODE = args.includes("--audit") ? "audit" : "switch";
const rest = args.filter((a) => !a.startsWith("--"));
const ONLY = (args.find((a) => a.startsWith("--only=")) || "").slice(7).split(",").filter(Boolean);
const REPEAT = Number((args.find((a) => a.startsWith("--repeat=")) || "--repeat=1").slice(9));
const WIDTH = Number(process.env.WIDTH || 360);
const EDGE = process.env.EDGE || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const { server, port } = await startServer();
const BASE = `http://127.0.0.1:${port}/?nosplash=1`;

// ---- browser ----------------------------------------------------------------------------
let edge = null, ws = null, id = 0;
const pending = new Map();
async function until(fn, ms = 10000, step = 100) {
  const t0 = Date.now();
  for (;;) { const v = await fn(); if (v) return v; if (Date.now() - t0 > ms) throw new Error("timeout waiting"); await new Promise((r) => setTimeout(r, step)); }
}
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const i = ++id;
  const timer = setTimeout(() => { pending.delete(i); reject(new Error("timeout: no answer to " + method + " within 60 s")); }, 60000);
  pending.set(i, (d) => { clearTimeout(timer); if (d.error) reject(new Error(method + ": " + d.error.message)); else resolve(d.result); });
  ws.send(JSON.stringify({ id: i, method, params }));
});
const ev = async (expr) => { const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error("eval: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text) + " :: " + expr.slice(0, 100)); return r.result.value; };
const waitEv = (expr, ms = 8000) => until(() => ev(expr), ms);
async function startBrowser() {
  const profile = mkdtempSync(path.join(os.tmpdir(), "edge-audit-"));
  const PORT = 9333 + Math.floor(Math.random() * 500);
  edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
  const target = await until(async () => { try { const j = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); return j.find((t) => t.type === "page"); } catch { return null; } }, 20000, 300);
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } };
  await send("Page.enable"); await send("Runtime.enable");
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await send("Emulation.setDeviceMetricsOverride", { width: WIDTH, height: 800, deviceScaleFactor: 1, mobile: true });
  await send("Page.addScriptToEvaluateOnNewDocument", { source: INIT_SOURCE });
}
function killBrowser() { try { ws.close(); } catch { /* closed */ } if (edge) spawnSync("taskkill", ["/PID", String(edge.pid), "/T", "/F"], { stdio: "ignore" }); pending.clear(); }
await startBrowser();

// ---- page helpers --------------------------------------------------------------------------
const q = (sel) => JSON.stringify(sel);
const click = (sel) => ev(`document.querySelector(${q(sel)}).click()`);
const vis = (sel) => `(() => { const e = document.querySelector(${q(sel)}); return !!e && !e.hidden && !e.closest("[hidden]"); })()`;
const waitVis = (sel, ms) => waitEv(vis(sel), ms);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const confirmAll = () => ev(`(() => { for (let n = 0; n < 40; n++) { const b = [...document.querySelectorAll("#screen-review button.confirm-btn:not(.is-confirmed)")][0]; if (!b) break; b.click(); } })()`);
const fillCosts = () => ev(`for (const [id, v] of [["input-fuel", "3"], ["input-maintenance", "1"]]) { const e = document.getElementById(id); if (e.value === "") { e.value = v; e.dispatchEvent(new Event("input")); } }`);
const fillWeekly = () => ev(`(() => { const nums = [...document.querySelectorAll("#review-groups input[type=number]")].slice(-2); const vals = ["300", "42"]; nums.forEach((e, i) => { if (e.value === "") { e.value = vals[i]; e.dispatchEvent(new Event("input")); } }); })()`);
const sample = async (kind) => { await click("#btn-try-sample"); await click(`[data-sample="${kind}"] button`); };
const setLang = async (lang) => {
  await ev(`(() => { const s = document.getElementById("lang-select-header"); s.value = ${q(lang)}; s.dispatchEvent(new Event("change")); })()`);
  await waitEv(`document.documentElement.lang === ${q(lang)}`, 5000);
  await sleep(500);
};
async function toResults(kind = "trip") {
  await sample(kind); await waitVis("#screen-review");
  if (kind === "weekly") await fillWeekly();
  await confirmAll(); await click("#btn-review-continue");
  await sleep(300);
  if (await ev(vis("#reconciliation-gate"))) await click("#btn-recon-continue-anyway"); // weekly gap panel: carry on to Costs
  await waitVis("#screen-costs"); await fillCosts(); await click("#btn-save-costs");
  await waitVis("#screen-results"); await sleep(900);
}
const toAsk = async () => { await toResults("trip"); await click("#nav-ask"); await waitVis("#screen-ask"); };
const mic = async (mode, say = "") => ev(`(async () => { window.__srMode = ${q(mode)}; window.__say = ${q(say)}; document.getElementById("btn-voice").click(); await new Promise((r) => setTimeout(r, 450)); })()`);

// Every screen and state. `expect(lang)` (optional) says what a specific element must show.
const STATES = [
  { id: "landing", go: async () => {} },
  { id: "samples-open", go: async () => { await click("#btn-try-sample"); } },
  { id: "rejected-order-offer", go: async () => { await sample("order_offer"); await waitVis("#screen-rejected"); }, expect: (l) => ({ sel: "#rejected-reason", text: l === "en" ? "This is an incoming order offer, not a completed trip." : dict[l]["rejected.orderOffer"] }) },
  { id: "rejected-other", go: async () => { modes.extractType = "other"; await sample("trip"); await waitVis("#screen-rejected"); }, expect: (l) => ({ sel: "#rejected-reason", text: l === "en" ? "This is a welcome or informational screen, not an earnings screen." : dict[l]["rejected.notAScreen"] }) },
  { id: "rejected-quality", go: async () => { modes.extractType = "quality"; await sample("trip"); await waitVis("#screen-rejected"); } },
  { id: "rejected-upload-415", go: async () => { modes.extractType = "err415"; await sample("trip"); await waitVis("#screen-rejected"); }, expect: (l) => ({ sel: "#rejected-reason", text: l === "en" ? "Please upload a PNG, JPEG or WebP image." : dict[l]["errors.badType"] }) },
  { id: "rejected-unreadable-400", go: async () => { modes.extractType = "err400"; await sample("trip"); await waitVis("#screen-rejected"); }, expect: (l) => ({ sel: "#rejected-reason", text: l === "en" ? "Could not read that image. Please upload a clear screenshot." : dict[l]["errors.unreadableImage"] }) },
  { id: "review-trip", go: async () => { await sample("trip"); await waitVis("#screen-review"); } },
  { id: "review-trip-confirmed", go: async () => { await sample("trip"); await waitVis("#screen-review"); await confirmAll(); } },
  { id: "review-weekly", go: async () => { await sample("weekly"); await waitVis("#screen-review"); } },
  { id: "gate-trip", go: async () => { modes.reconFlag = true; await sample("trip"); await waitVis("#screen-review"); await confirmAll(); await click("#btn-review-continue"); await waitVis("#trip-reconciliation-gate"); } },
  { id: "gate-weekly", go: async () => { modes.weeklyGap = true; await sample("weekly"); await waitVis("#screen-review"); await fillWeekly(); await confirmAll(); await click("#btn-review-continue"); await waitVis("#reconciliation-gate"); } },
  { id: "costs", go: async () => { await sample("trip"); await waitVis("#screen-review"); await confirmAll(); await click("#btn-review-continue"); await waitVis("#screen-costs"); } },
  { id: "results-trip", go: async () => { await toResults("trip"); } },
  { id: "results-weekly", go: async () => { modes.weeklyGap = true; await toResults("weekly"); } },
  { id: "ask", go: async () => { await toAsk(); } },
  { id: "ask-answered", go: async () => { await toAsk(); await click("#ask-suggestions button"); await waitVis("#ask-answer"); } },
  { id: "voice-listening", go: async () => { await toAsk(); await ev(`window.__srMode = "speak"; window.__say = "x"; document.getElementById("btn-voice").click()`); await sleep(200); } },
  { id: "voice-denied", go: async () => { await toAsk(); await mic("denied"); } },
  { id: "voice-no-speech", go: async () => { await toAsk(); await mic("nospeech"); } },
  { id: "voice-network", go: async () => { await toAsk(); await mic("network"); } },
  { id: "voice-transcript", go: async () => { await toAsk(); await ev(`window.__srMode = "speak"; window.__say = "what was my net pay per hour"; document.getElementById("btn-voice").click()`); await sleep(200); await click("#btn-voice"); await sleep(300); } },
  { id: "evidence", go: async () => { await toResults("trip"); await click("#nav-evidence"); await waitVis("#screen-evidence"); } },
  { id: "delete-confirm", go: async () => { await toResults("trip"); await click("#nav-evidence"); await waitVis("#screen-evidence"); await click("#btn-delete-data"); } },
  { id: "after-delete-toast", go: async () => { await toResults("trip"); await click("#nav-evidence"); await waitVis("#screen-evidence"); await click("#btn-delete-data"); await click("#btn-delete-confirm-yes"); await waitVis("#screen-landing"); await waitVis("#toast", 3000); } },
  { id: "error-503-busy", go: async () => { await errorAtResults(503, "service_busy"); }, expect: (l) => ({ sel: "#toast", text: dict[l]["errors.busy"] }) },
  { id: "error-429-daily-limit", go: async () => { await errorAtResults(429, "daily_limit_reached"); }, expect: (l) => ({ sel: "#toast", text: l === "en" ? "BACKEND ENGLISH MESSAGE" : dict[l]["errors.dailyLimit"] }) },
  { id: "error-400-no-trips", go: async () => { await errorAtResults(400, "no_trips"); }, expect: (l) => ({ sel: "#toast", text: l === "en" ? "BACKEND ENGLISH MESSAGE" : dict[l]["errors.noTrips"] }) },
];
async function errorAtResults(status, code) {
  await sample("trip"); await waitVis("#screen-review"); await confirmAll(); await click("#btn-review-continue");
  await waitVis("#screen-costs"); await fillCosts();
  modes.summaryError = { status, code };
  await click("#btn-save-costs"); await waitVis("#toast", 4000); await sleep(200);
}

// ---- collecting text ---------------------------------------------------------------------------
const COLLECT = `(() => {
  const out = [];
  const add = (kind, text, where) => { text = String(text || "").replace(/\\s+/g, " ").trim(); if (text) out.push({ kind, text, where }); };
  const hiddenEl = (el) => { for (let e = el; e; e = e.parentElement) { if (e.hidden) return true; const cs = getComputedStyle(e); if (cs.display === "none" || cs.visibility === "hidden") return true; } return false; };
  const skip = "script,style,option,.visually-hidden,#version-stamp,#splash";
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement; if (!el || el.closest(skip) || hiddenEl(el)) continue;
    add("text", n.nodeValue, (el.closest("[id]") || el).id || el.tagName.toLowerCase());
  }
  for (const el of document.querySelectorAll("[placeholder],[aria-label],[title],img[alt]")) {
    if (el.closest(skip) || hiddenEl(el)) continue;
    for (const a of ["placeholder", "aria-label", "title", "alt"]) if (el.getAttribute(a)) add(a, el.getAttribute(a), el.id || el.tagName.toLowerCase());
  }
  add("title", document.title, "document");
  return out;
})()`;

const SCRIPTS = { hi: /[\u0900-\u097F]/, ta: /[\u0B80-\u0BFF]/, te: /[\u0C00-\u0C7F]/, kn: /[\u0C80-\u0CFF]/, ml: /[\u0D00-\u0D7F]/ };
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const templateRe = (v) => new RegExp("^" + esc(v).replace(/\\\{\w+\\\}/g, ".+?") + "$");
const hasLetter = (s) => /\p{L}/u.test(s);

async function fresh(lang) {
  modes.reconFlag = false; modes.extractType = null; modes.summaryError = null; modes.weeklyGap = false;
  try { await ev(`sessionStorage.clear()`); } catch { /* first page: nothing to clear */ }
  await send("Page.navigate", { url: BASE });
  await waitVis("#screen-landing", 15000);
  if (lang !== "en") await setLang(lang); else await sleep(300);
}

let total = 0, failures = 0;
const T0 = Date.now();
function line(parts, ok, secs, extra = "") { total += 1; if (!ok) failures += 1; console.log(`${parts} | ${ok ? "pass" : "FAIL"} | ${secs.toFixed(1)}s${extra ? " | " + extra : ""}`); }
async function guarded(label, fn) {
  const t0 = Date.now();
  try { return await fn(); } catch (err) {
    const msg = String(err.message || err).slice(0, 200);
    line(label, false, (Date.now() - t0) / 1000, "ERROR " + msg);
    if (/timeout/i.test(msg)) {
      let alive = "no";
      try { await Promise.race([ev("1 + 1"), new Promise((_, rej) => setTimeout(() => rej(new Error("probe timeout")), 5000))]); alive = "yes"; } catch { /* stays no */ }
      console.log(`  probe after timeout: page still answers a trivial script: ${alive}`);
      killBrowser(); await startBrowser();
    }
    return null;
  }
}

if (MODE === "switch") {
  const PAIRS = (rest.length ? rest : ["en>ta", "ta>en", "hi>ml", "ml>hi", "te>kn", "kn>te"]).map((p) => p.split(">"));
  for (const [A, B] of PAIRS) {
    // texts that belong to language A's file and differ in B's file, as exact strings or templates
    const owned = [];
    for (const [k, v] of Object.entries(dict[A])) if (dict[B][k] !== v && typeof v === "string") owned.push({ k, v, re: v.includes("{") ? templateRe(v) : null });
    for (const st of STATES.filter((x) => !ONLY.length || ONLY.includes(x.id)).flatMap((x) => Array(REPEAT).fill(x))) {
      const label = `${A}>${B} ${st.id}`;
      const t0 = Date.now();
      const result = await guarded(label, async () => {
        await fresh(A); await st.go();
        const before = await ev(COLLECT);
        await setLang(B);
        const after = await ev(COLLECT);
        const problems = [];
        for (const t of after) {
          if (!hasLetter(t.text)) continue;
          const hit = owned.find((o) => (o.re ? o.re.test(t.text) : t.text === o.v) || (o.v.length >= 8 && !o.re && t.text.includes(o.v)));
          if (hit) problems.push(`"${t.text.slice(0, 60)}" (${t.where}) still ${A} text of key ${hit.k}`);
          else if (SCRIPTS[A] && !SCRIPTS[B] && SCRIPTS[A].test(t.text)) problems.push(`"${t.text.slice(0, 60)}" (${t.where}) still ${A} script`);
          else if (SCRIPTS[A] && SCRIPTS[B] && SCRIPTS[A].test(t.text)) problems.push(`"${t.text.slice(0, 60)}" (${t.where}) still ${A} script`);
        }
        if (st.expect) {
          const e = st.expect(B);
          const got = await ev(`(document.querySelector(${q(e.sel)}) || {}).textContent || ""`);
          if (got.trim() !== e.text) problems.push(`${e.sel} shows "${got.trim().slice(0, 70)}" but should show "${String(e.text).slice(0, 70)}"`);
        }
        return { problems, n: before.length };
      });
      if (result) line(label, result.problems.length === 0, (Date.now() - t0) / 1000, result.problems.slice(0, 4).join(" ;; "));
    }
  }
} else {
  const LANGS = rest.length ? rest : ["hi", "ta", "te", "kn", "ml"];
  const ALLOWED_LATIN = /\b(PayProof|Chrome|Google|Edge|TrailDash|ZipGo|km|ID|PNG|JPEG|WebP|MB|AM|PM)\b/g;
  const enValues = new Map(); // text/template -> key
  for (const [k, v] of Object.entries(dict.en)) enValues.set(k, { v, re: v.includes("{") ? templateRe(v) : null });
  const backendSet = new Set(BACKEND_ENGLISH.concat(["Distance driven was not provided, so pay per km is not shown."]));
  const rows = [];
  for (const L of LANGS) {
    for (const st of STATES) {
      const t0 = Date.now();
      const label = `audit ${L} ${st.id}`;
      const found = await guarded(label, async () => {
        await fresh(L); await st.go();
        return ev(COLLECT);
      });
      if (!found) continue;
      const bad = [];
      for (const t of found) {
        if (!hasLetter(t.text)) continue;
        const isBackend = [...backendSet].some((b) => t.text === b || t.text.includes(b));
        const sameAsEn = [...enValues.entries()].find(([k, o]) => (o.re ? o.re.test(t.text) : t.text === o.v) && dict[L][k] === o.v && o.v.replace(ALLOWED_LATIN, "").match(/[A-Za-z]{2,}/));
        // a technical error_code in parentheses, e.g. "(server_error)", is not a sentence: allowed
        const noLetterAfterAllowed = !t.text.replace(/\([a-z_]+\)/g, "").replace(ALLOWED_LATIN, "").match(/[A-Za-z]{2,}/);
        let source = null;
        if (noLetterAfterAllowed) source = null; // only brand words, abbreviations or non-Latin text
        else if (isBackend) source = "backend text / data";
        else if (sameAsEn) source = `missing key (${sameAsEn[0]} is English in ${L}.json)`;
        else source = "hard-coded or untranslated Latin text";
        if (source) bad.push({ language: L, screen: st.id, text: t.text.slice(0, 90), kind: t.kind, source });
      }
      rows.push(...bad);
      const real = bad.filter((b) => !b.source.startsWith("backend"));
      line(label, real.length === 0, (Date.now() - t0) / 1000, `${found.length} texts; ${bad.length - real.length} backend/data; ${real.length} to fix${real.length ? ": " + real.slice(0, 3).map((r) => `"${r.text.slice(0, 40)}" [${r.source}]`).join(" ;; ") : ""}`);
    }
  }
  const out = path.join(os.tmpdir(), "payproof-english-leak-audit.json");
  writeFileSync(out, JSON.stringify(rows, null, 1));
  const uniq = new Map();
  for (const r of rows) { const k = `${r.language}|${r.source}|${r.text}`; if (!uniq.has(k)) uniq.set(k, { ...r, screens: new Set() }); uniq.get(k).screens.add(r.screen); }
  console.log("\nTABLE language | screens | text | source");
  for (const r of uniq.values()) console.log(`${r.language} | ${[...r.screens].slice(0, 4).join(",")}${r.screens.size > 4 ? ",…" : ""} | ${r.text} | ${r.source}`);
  console.log(`saved ${out}`);
}

console.log(`\nchecks: ${total}, failures: ${failures}, seconds: ${Math.round((Date.now() - T0) / 1000)}`);
killBrowser(); server.close();
process.exit(failures ? 1 : 0);
