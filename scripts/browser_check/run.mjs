// Drives the real frontend in headless Edge over the Chrome DevTools Protocol (no npm packages).
// Dev-only (not deployed). Serves frontend/ with Firebase and /api stubbed (no network, no Gemini) and
// drives every screen in headless Edge: layout overflow, text-vs-shadow overlap (counts per screen),
// digits 0-9, language switching, mic states (fake SpeechRecognition), header selector fit.
// usage: node scripts/browser_check/run.mjs [langs=en,hi,ta,te,kn,ml] [widths=320,360,390] [voice=1]
// env: SHOTS=<dir> saves 360 px screenshots (en, ta) there; TAG=<name> names the overlap detail JSON in the temp folder;
//      EDGE=<path to msedge.exe or chrome.exe>. Exit code 1 if any check fails; overlap hits are counted as checks too.
import { spawn } from "child_process";
import { mkdtempSync, writeFileSync, mkdirSync } from "fs";
import os from "os";
import path from "path";
import { startServer, counters, modes } from "./harness_server.mjs";

const LANGS = (process.argv[2] || "en,hi,ta,te,kn,ml").split(",");
const WIDTHS = (process.argv[3] || "320,360,390").split(",").map(Number);
const DO_VOICE = process.argv[4] !== "0";
const EDGE = process.env.EDGE || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const PORT = 9333 + Math.floor(Math.random() * 500);

const { server, port } = await startServer();
const BASE = `http://127.0.0.1:${port}/?nosplash=1`;
const profile = mkdtempSync(path.join(os.tmpdir(), "edge-prof-"));
const edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });

async function until(fn, ms = 10000, step = 100) {
  const t0 = Date.now();
  for (;;) { const v = await fn(); if (v) return v; if (Date.now() - t0 > ms) throw new Error("timeout waiting"); await new Promise((r) => setTimeout(r, step)); }
}
const targets = await until(async () => { try { const r = await fetch(`http://127.0.0.1:${PORT}/json`); const j = await r.json(); return j.find((t) => t.type === "page"); } catch { return null; } }, 20000, 300);
const ws = new WebSocket(targets.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const consoleErrors = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
  else if (d.method === "Runtime.exceptionThrown") consoleErrors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  else if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") consoleErrors.push(d.params.args.map((a) => a.value || a.description).join(" "));
};
const send = (method, params = {}) => new Promise((resolve, reject) => { const i = ++id; pending.set(i, (d) => (d.error ? reject(new Error(method + ": " + d.error.message)) : resolve(d.result))); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => { const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error("eval: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text) + " :: " + expr.slice(0, 120)); return r.result.value; };
const waitEv = (expr, ms) => until(() => ev(expr), ms);
await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setFocusEmulationEnabled", { enabled: true }); // headless pages are not focused by default; needed so :focus-visible rings exist

// Fake speech recognition + shortened 15 s timer, installed before every page load.
await send("Page.addScriptToEvaluateOnNewDocument", { source: `
  (() => {
    const realSetTimeout = window.setTimeout.bind(window);
    window.setTimeout = (fn, ms, ...a) => realSetTimeout(fn, ms === 15000 ? 400 : ms, ...a);
    window.__srCreated = 0;
    window.__srMode = "speak"; // speak | denied | nospeech | silence | network
    class FakeSR {
      constructor() { window.__sr = this; window.__srCreated += 1; this.log = []; }
      start() {
        this.log.push("start:" + this.lang);
        if (window.__srMode === "denied") { setTimeout(() => { this.onerror && this.onerror({ error: "not-allowed" }); this.onend && this.onend(); }, 20); return; }
        if (window.__srMode === "network") { setTimeout(() => { this.onerror && this.onerror({ error: "network" }); this.onend && this.onend(); }, 20); return; }
        setTimeout(() => this.onstart && this.onstart(), 20);
        if (window.__srMode === "nospeech") setTimeout(() => { this.onerror && this.onerror({ error: "no-speech" }); this.onend && this.onend(); }, 120);
        if (window.__srMode === "silence") setTimeout(() => { this.onend && this.onend(); }, 120);
      }
      stop() { this.log.push("stop"); setTimeout(() => { if (window.__say) this.onresult && this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: window.__say }], { isFinal: true })] }); this.onend && this.onend(); }, 10); }
      abort() { this.log.push("abort"); setTimeout(() => { this.onerror && this.onerror({ error: "aborted" }); this.onend && this.onend(); }, 10); }
    }
    window.SpeechRecognition = FakeSR;
  })();
` });

const overflowFn = `(() => {
  const vw = window.innerWidth, bad = [];
  const name = (el) => (el.id ? "#" + el.id : el.tagName.toLowerCase() + (el.className && typeof el.className === "string" ? "." + el.className.split(" ")[0] : "")) + " «" + (el.textContent || "").trim().slice(0, 30) + "»";
  if (document.documentElement.scrollWidth > vw + 1) bad.push("page scrollWidth " + document.documentElement.scrollWidth + " > " + vw);
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest("[hidden]") || el.closest("#splash") || el.closest(".visually-hidden") || el.closest("svg") && el.tagName.toLowerCase() !== "svg") continue;
    const cs = getComputedStyle(el); if (cs.display === "none" || cs.visibility === "hidden") continue;
    const r = el.getBoundingClientRect(); if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1 || r.left < -1) bad.push("outside viewport: " + name(el) + " [" + Math.round(r.left) + "," + Math.round(r.right) + "]");
    if (cs.display !== "inline" && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 4 && !el.matches("select,textarea,input")) bad.push("content wider than box: " + name(el) + " " + el.scrollWidth + ">" + el.clientWidth);
    if (el.matches("button, h1, h2, h3, h4, label") && cs.display !== "inline" && el.scrollHeight > el.clientHeight + 2 && cs.overflowY !== "visible") bad.push("clipped height: " + name(el));
  }
  const nonLatin = [...document.body.innerText.matchAll(/\\p{Nd}/gu)].map((m) => m[0]).filter((c) => !/[0-9]/.test(c));
  if (nonLatin.length) bad.push("non 0-9 digits: " + [...new Set(nonLatin)].join(""));
  return bad;
})()`;

const overlapFn = `(() => {
  const CLEAR = 3.9;
  const TEXT = "h1,h2,h3,h4,label,button,p,li,.date-human,.step-dot-label,.money-chart-label,.money-chart-value,.rate-card-value,.net-earnings-value,.results-row .label,.results-row .value";
  const BOX = TEXT + ",input,textarea,select,.card,.sample-card,.banner,.error-banner,.landing-hero,.results-hero,img.preview,.step-dot-num,.verified-badge";
  const skip = ".app-nav,#toast,#error-line,#loading-overlay,#splash,.lightbox,svg";
  const items = [];
  for (const el of document.querySelectorAll(BOX)) {
    if (el.closest("[hidden]") || el.closest(skip) || el.closest(".visually-hidden")) continue;
    const cs = getComputedStyle(el); if (cs.display === "none" || cs.visibility === "hidden") continue;
    const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
    const regions = [];
    for (const m of cs.boxShadow.matchAll(/(-?[\\d.]+)px (-?[\\d.]+)px (-?[\\d.]+)px(?: (-?[\\d.]+)px)?/g)) {
      const x = +m[1], y = +m[2], sp = +(m[4] || 0);
      if (x === 0 && y === 0 && sp === 0) continue;
      regions.push({ kind: "shadow", l: r.left + x - sp, t: r.top + y - sp, r: r.right + x + sp, b: r.bottom + y + sp });
    }
    if (el === document.activeElement && cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) {
      const ring = parseFloat(cs.outlineWidth) + parseFloat(cs.outlineOffset || 0);
      regions.push({ kind: "focus ring", l: r.left - ring, t: r.top - ring, r: r.right + ring, b: r.bottom + ring });
    }
    items.push({ el, text: el.matches(TEXT), rect: { kind: "box", l: r.left, t: r.top, r: r.right, b: r.bottom }, regions });
  }
  const hit = (a, b, grow) => Math.min(a.r + grow, b.r) - Math.max(a.l - grow, b.l) > 0.5 && Math.min(a.b + grow, b.b) - Math.max(a.t - grow, b.t) > 0.5;
  const name = (el) => (el.id ? "#" + el.id : el.tagName.toLowerCase() + (typeof el.className === "string" && el.className ? "." + el.className.split(" ")[0] : "")) + "«" + (el.textContent || "").trim().slice(0, 18).replace(/\\s+/g, " ") + "»";
  const tightPair = (a, b) => { const fa = a.closest(".field"), fb = b.closest(".field"); return fa && fa === fb && (a.matches("label,.hint,.date-human") || b.matches("label,.hint,.date-human")); };
  const hits = []; const sig = new Set();
  for (const A of items) {
    if (!A.text) continue;
    for (const B of items) {
      if (A === B || A.el.contains(B.el) || B.el.contains(A.el) || tightPair(A.el, B.el)) continue;
      for (const reg of [B.rect, ...B.regions]) {
        if (hit(A.rect, reg, reg.kind === "box" ? 0 : CLEAR)) { const k = name(A.el) + " | " + name(B.el) + " (" + reg.kind + ")"; const k2 = name(B.el) + " | " + name(A.el); if (!sig.has(k) && !sig.has(k2)) { sig.add(k); hits.push(k); } break; }
      }
    }
  }
  return hits;
})()`;
const overlapHits = {};
const overlapDetail = {};
const overlapCombos = {};
const SHOTS = process.env.SHOTS;
let shotsDir = null; if (SHOTS) { shotsDir = SHOTS; mkdirSync(shotsDir, { recursive: true }); }
async function checkOverlap(lang, width, step) {
  const hits = await ev(overlapFn);
  record(lang, width, step + " overlap", hits.length === 0, hits.slice(0, 4).join(" ;; "));
  overlapHits[step] = (overlapHits[step] || 0) + hits.length;
  if (hits.length) { overlapCombos[step] = (overlapCombos[step] || 0) + 1; (overlapDetail[step] ||= []).push(`${lang}/${width}: ` + hits.join(" ;; ")); }
  if (shotsDir && width === 360 && (lang === "en" || lang === "ta")) {
    const h = await ev("Math.max(document.documentElement.scrollHeight, 800)");
    const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width, height: Math.min(h, 4000), scale: 1 } });
    writeFileSync(path.join(shotsDir, `${lang}-${step.replace(/[^a-z0-9]+/gi, "_")}.png`), Buffer.from(shot.data, "base64"));
  }
}

const results = []; let failures = 0;
const T0 = Date.now();
function record(lang, width, step, ok, detail = "") { if (process.env.VERBOSE) console.log(`[${Math.round((Date.now() - T0) / 1000)}s] ${lang} ${width} ${step} ${ok ? "ok" : "FAIL"}`); results.push({ lang, width, step, ok, detail }); if (!ok) { failures += 1; console.log(`FAIL [${lang} ${width}px] ${step} ${detail}`); } }
async function checkOverflow(lang, width, step) { const bad = await ev(overflowFn); record(lang, width, step + " layout", bad.length === 0, bad.slice(0, 6).join(" | ")); await checkOverlap(lang, width, step); }
const click = (sel) => ev(`document.querySelector(${JSON.stringify(sel)}).click()`);
const visible = (sel) => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); return !!e && !e.hidden && !e.closest("[hidden]"); })()`;
const confirmAll = () => ev(`(async () => { for (let n = 0; n < 40; n++) { const b = [...document.querySelectorAll("#screen-review button.confirm-btn:not(.is-confirmed)")][0]; if (!b) break; b.click(); } return !document.getElementById("btn-review-continue").disabled; })()`);

async function load(lang, width) {
  await send("Emulation.setDeviceMetricsOverride", { width, height: 800, deviceScaleFactor: 1, mobile: true });
  await send("Page.navigate", { url: BASE });
  await waitEv(visible("#screen-landing"), 15000);
  await ev(`(() => { const s = document.getElementById("lang-select-header"); s.value = ${JSON.stringify(lang)}; s.dispatchEvent(new Event("change")); })()`);
  await waitEv(`document.documentElement.lang === ${JSON.stringify(lang)} && document.getElementById("landing-headline").textContent.length > 0`, 5000);
  await new Promise((r) => setTimeout(r, 150));
}

for (const lang of LANGS) {
  for (const width of WIDTHS) {
    try {
      modes.reconFlag = false;
      await load(lang, width);
      const info = await ev(`({ htmlLang: document.documentElement.lang, stored: sessionStorage.getItem("payproof_lang"), headerSel: document.getElementById("lang-select-header").value, landingSel: (document.getElementById("lang-select-landing") || {}).value || null, note: !document.getElementById("machine-note").hidden, noteText: document.getElementById("machine-note").textContent, font: getComputedStyle(document.body).fontFamily.split(",")[0], headline: document.getElementById("landing-headline").textContent, title: document.title })`);
      record(lang, width, "language state", info.htmlLang === lang && info.stored === lang && info.headerSel === lang && info.landingSel === null && info.note === (lang !== "en") && info.headline.length > 0, JSON.stringify(info));
      const fit = await ev(`(() => { const s = document.getElementById("lang-select-header").getBoundingClientRect(), h = document.getElementById("btn-home").getBoundingClientRect(); return { sameRow: Math.abs((s.top + s.bottom) / 2 - (h.top + h.bottom) / 2) < 6, inView: s.left >= 0 && h.right <= window.innerWidth, selW: Math.round(s.width) }; })()`);
      record(lang, width, "header selector fits beside Home", fit.sameRow && fit.inView, JSON.stringify(fit));
      if (width === WIDTHS[0]) console.log(`${lang}: font=${info.font} note=${info.note} "${info.noteText}" headline="${info.headline}"`);
      await checkOverflow(lang, width, "first screen");
      const broken = await ev(`[...document.querySelectorAll(".step-dot-label")].filter((el) => { const words = el.textContent.trim().split(/\s+/).length; const lh = parseFloat(getComputedStyle(el).lineHeight) || 14; return Math.round(el.getBoundingClientRect().height / lh) > words; }).map((el) => el.textContent)`);
      record(lang, width, "step labels not broken mid-word", broken.length === 0, broken.join(","));
      await click("#btn-try-sample"); await checkOverflow(lang, width, "first screen + samples");

      // trip sample -> review -> costs -> results
      await ev(`document.querySelectorAll("#sample-cards button")[0].click()`);
      await waitEv(visible("#screen-review"), 8000);
      const dateTxt = await ev(`document.querySelector(".date-human").textContent`);
      record(lang, width, "date text", /^\d{1,2} \S+ 2026$/.test(dateTxt) && /^[\x20-\x7E\u0900-\u0DFF\u200c\u200d\u0964]+$/.test(dateTxt) && !/[०-९௦-௯౦-౯೦-೯൦-൯]/.test(dateTxt), dateTxt);
      await checkOverflow(lang, width, "review (unconfirmed)");
      const ready = await confirmAll(); record(lang, width, "review confirmable", ready);
      await checkOverflow(lang, width, "review (confirmed)");
      await click("#btn-review-continue"); await waitEv(visible("#screen-costs"), 8000);
      await checkOverflow(lang, width, "costs");
      await click("#btn-save-costs"); await waitEv(visible("#screen-results"), 8000);
      await new Promise((r) => setTimeout(r, 900));
      const res = await ev(`document.getElementById("results-body").innerText`);
      record(lang, width, "results figures", /₹7,823\.00/.test(res) && /₹195\.58/.test(res) && /₹30\.08/.test(res) && /5\.9%/.test(res), res.replace(/\n/g, " ").slice(0, 160));
      await checkOverflow(lang, width, "results");

      // language switch on Results keeps figures
      const other = lang === "en" ? "ta" : "en";
      await ev(`(() => { const s = document.getElementById("lang-select-header"); s.value = ${JSON.stringify(other)}; s.dispatchEvent(new Event("change")); })()`);
      await waitEv(`document.documentElement.lang === ${JSON.stringify(other)}`, 4000); await new Promise((r) => setTimeout(r, 900));
      const res2 = await ev(`document.getElementById("results-body").innerText`);
      record(lang, width, "figures unchanged after switching to " + other, /₹7,823\.00/.test(res2) && /₹195\.58/.test(res2), res2.replace(/\n/g, " ").slice(0, 120));
      await ev(`(() => { const s = document.getElementById("lang-select-header"); s.value = ${JSON.stringify(lang)}; s.dispatchEvent(new Event("change")); })()`);
      await waitEv(`document.documentElement.lang === ${JSON.stringify(lang)}`, 4000); await new Promise((r) => setTimeout(r, 900));

      // ask
      await click("#nav-ask"); await waitEv(visible("#screen-ask"), 4000);
      const micShown = await ev(`!document.getElementById("btn-voice").hidden`);
      record(lang, width, "mic button visible when supported", micShown);
      await checkOverflow(lang, width, "ask");
      const askBefore = counters.ask;
      await click("#ask-suggestions button");
      await waitEv(visible("#ask-answer"), 6000);
      record(lang, width, "suggested question answered", counters.ask === askBefore + 1 && (await ev(`document.getElementById("ask-answer-text").textContent`)).includes("195.58"));
      await checkOverflow(lang, width, "ask (answered)");

      if (DO_VOICE) {
        // mic: speak, second tap stops, text lands in box, NOT submitted
        const sp = await ev(`(async () => { window.__srMode = "speak"; window.__say = "what was my net pay per hour"; document.getElementById("input-ask-question").value = "old question"; document.getElementById("btn-voice").click(); await new Promise(r => setTimeout(r, 150)); const mid = { listening: document.getElementById("btn-voice").classList.contains("listening"), status: document.getElementById("voice-status").textContent, pressed: document.getElementById("btn-voice").getAttribute("aria-pressed"), label: document.getElementById("btn-voice").getAttribute("aria-label"), srLang: window.__sr.lang }; return mid; })()`);
        record(lang, width, "mic listening state", sp.listening && sp.pressed === "true" && sp.status.length > 0, JSON.stringify(sp));
        const asksBeforeVoice = counters.ask;
        await checkOverflow(lang, width, "ask (listening)");
        await click("#btn-voice"); await new Promise((r) => setTimeout(r, 200));
        const after = await ev(`({ text: document.getElementById("input-ask-question").value, note: !document.getElementById("voice-check-note").hidden, noteText: document.getElementById("voice-check-note").textContent, listening: document.getElementById("btn-voice").classList.contains("listening"), privacy: document.getElementById("voice-privacy").textContent, privacyShown: !document.getElementById("voice-privacy").hidden })`);
        const speechCodes = { en: "en-IN", hi: "hi-IN", ta: "ta-IN", te: "te-IN", kn: "kn-IN", ml: "ml-IN" };
        record(lang, width, "mic transcript in box, check note shown, never auto-submitted", after.text === "what was my net pay per hour" && after.note && !after.listening && counters.ask === asksBeforeVoice && after.privacyShown, JSON.stringify(after));
        record(lang, width, "recognition language", sp.srLang === speechCodes[lang], sp.srLang);
        const ring = await ev(`(() => { const t = document.getElementById("input-ask-question"), c = getComputedStyle(t); return { focused: document.activeElement === t, style: c.outlineStyle, width: c.outlineWidth, offset: c.outlineOffset }; })()`);
        record(lang, width, "textarea has its focus ring after a transcript (so the overlap check measures it)", ring.focused && ring.style !== "none" && parseFloat(ring.width) > 0, JSON.stringify(ring));
        await checkOverflow(lang, width, "ask (transcript + notes)");
        for (const [mode, label] of [["denied", "permission refused"], ["nospeech", "no speech"], ["silence", "silence stop"], ["network", "network error"]]) {
          const out = await ev(`(async () => { window.__srMode = ${JSON.stringify(mode)}; window.__say = ""; document.getElementById("btn-voice").click(); await new Promise(r => setTimeout(r, 400)); return { status: document.getElementById("voice-status").textContent, listening: document.getElementById("btn-voice").classList.contains("listening"), shown: !document.getElementById("voice-status").hidden }; })()`);
          record(lang, width, "mic " + label + " shows plain message and stops", out.shown && out.status.length > 5 && !out.listening, JSON.stringify(out));
        }
        await checkOverflow(lang, width, "ask (voice error)");
        // 15 s cap (shortened to 0.4 s by the harness): listening starts, no end from the browser, our timer stops it
        const cap = await ev(`(async () => { window.__srMode = "speak"; window.__say = "capped words"; document.getElementById("btn-voice").click(); await new Promise(r => setTimeout(r, 150)); const was = document.getElementById("btn-voice").classList.contains("listening"); await new Promise(r => setTimeout(r, 700)); return { was, now: document.getElementById("btn-voice").classList.contains("listening"), text: document.getElementById("input-ask-question").value, log: window.__sr.log.join(",") }; })()`);
        record(lang, width, "mic stops itself at the time limit", cap.was && !cap.now && cap.text === "capped words", JSON.stringify(cap));
        // leaving the screen while listening cancels and drops the words
        const leave = await ev(`(async () => { window.__srMode = "speak"; window.__say = "should not appear"; document.getElementById("input-ask-question").value = "keep"; document.getElementById("btn-voice").click(); await new Promise(r => setTimeout(r, 100)); document.getElementById("nav-evidence").click(); await new Promise(r => setTimeout(r, 200)); document.getElementById("nav-ask").click(); return { text: document.getElementById("input-ask-question").value, listening: document.getElementById("btn-voice").classList.contains("listening") }; })()`);
        record(lang, width, "mic cancelled when leaving the screen", leave.text === "keep" && !leave.listening, JSON.stringify(leave));
      }

      // evidence + delete
      await click("#nav-evidence"); await waitEv(visible("#screen-evidence"), 4000);
      await checkOverflow(lang, width, "evidence");
      await click("#btn-delete-data"); await checkOverflow(lang, width, "evidence (delete confirm)");
      await click("#btn-delete-confirm-yes"); await waitEv(visible("#screen-landing"), 5000);
      record(lang, width, "delete returns to first screen", true);

      // weekly sample
      await click("#btn-try-sample"); await ev(`document.querySelectorAll("#sample-cards button")[1].click()`);
      await waitEv(visible("#screen-review"), 8000);
      await checkOverflow(lang, width, "review weekly (unconfirmed)");
      await confirmAll(); await checkOverflow(lang, width, "review weekly (confirmed)");
      await click("#btn-review-continue"); await waitEv(visible("#screen-costs"), 8000);
      await click("#btn-save-costs"); await waitEv(visible("#screen-results"), 8000); await new Promise((r) => setTimeout(r, 900));
      await checkOverflow(lang, width, "results weekly");
      await click("#nav-ask"); await waitEv(visible("#screen-ask"), 3000); await checkOverflow(lang, width, "ask weekly");
      await click("#btn-home");  // home
      await waitEv(visible("#screen-landing"), 4000);

      // rejected
      await click("#btn-try-sample"); await ev(`document.querySelectorAll("#sample-cards button")[2].click()`);
      await waitEv(visible("#screen-rejected"), 8000); await checkOverflow(lang, width, "rejected");
      await click("#btn-try-another"); await waitEv(visible("#screen-landing"), 4000);

      // reconciliation gate + language switch keeps it open
      modes.reconFlag = true;
      await click("#btn-try-sample"); await ev(`document.querySelectorAll("#sample-cards button")[0].click()`);
      await waitEv(visible("#screen-review"), 8000); await confirmAll(); await click("#btn-review-continue");
      await waitEv(visible("#trip-reconciliation-gate"), 6000); await checkOverflow(lang, width, "trip reconciliation gate");
      const gateText1 = await ev(`document.getElementById("trip-reconciliation-gate-text").textContent`);
      await ev(`(() => { const s = document.getElementById("lang-select-header"); s.value = ${JSON.stringify(lang === "hi" ? "ta" : "hi")}; s.dispatchEvent(new Event("change")); })()`);
      await new Promise((r) => setTimeout(r, 400));
      const gate2 = await ev(`({ open: !document.getElementById("trip-reconciliation-gate").hidden, text: document.getElementById("trip-reconciliation-gate-text").textContent })`);
      record(lang, width, "gate stays open and is re-translated on switch", gate2.open && gate2.text !== gateText1 && /147\.02/.test(gate2.text) && /136\.65/.test(gate2.text), gate2.text.slice(0, 80));
      modes.reconFlag = false;
    } catch (err) {
      record(lang, width, "scenario", false, String(err.message || err).slice(0, 300));
    }
  }
}

// API error-code mapping (non-English uses translated keys, English keeps backend message)
for (const lang of ["en", "hi"]) {
  await load(lang, 390);
  const out = await ev(`(async () => {
    const { api } = await import("/api.js");
    const r = {};
    for (const [status, code] of [[415,"unsupported_file_type"],[413,"file_too_large"],[503,"service_busy"],[429,"daily_limit_reached"],[400,"no_trips"],[401,"invalid_token"],[400,"unreadable_image"]]) {
      try { await fetch("/api/err/" + status + "/" + code); } catch (e) {}
    }
    return r;
  })()`);
}
const mapTest = await ev(`(async () => {
  const mod = await import("/api.js");
  const orig = window.fetch;
  const out = {};
  for (const lang of ["en", "hi"]) {
    const i18n = await import("/i18n.js"); await i18n.setLanguage(lang);
    for (const [status, code] of [[415,"unsupported_file_type"],[413,"file_too_large"],[503,"service_busy"],[429,"daily_limit_reached"],[400,"no_trips"],[401,"invalid_token"],[400,"unreadable_image"]]) {
      window.fetch = (p, o) => orig("/api/err/" + status + "/" + code, o);
      try { await mod.api.deleteAll(); } catch (e) { out[lang + ":" + status + ":" + code] = e.message; }
    }
  }
  window.fetch = orig; return out;
})()`);
console.log("error mapping:", JSON.stringify(mapTest, null, 1));
console.log("\nOVERLAP HITS per screen (sum over languages x widths; combos with a hit):");
for (const k of Object.keys(overlapHits)) console.log(`  ${k}: ${overlapHits[k]} hits in ${overlapCombos[k] || 0} combos`);
console.log("  TOTAL:", Object.values(overlapHits).reduce((a, b) => a + b, 0));
writeFileSync(path.join(os.tmpdir(), "overlap-detail-" + (process.env.TAG || "run") + ".json"), JSON.stringify({ overlapHits, overlapCombos, overlapDetail }, null, 1));
writeFileSync(path.join(os.tmpdir(), "drive-results.json"), JSON.stringify(results, null, 1));
console.log(`\nchecks: ${results.length}, failures: ${failures}, page errors: ${consoleErrors.length}`);
consoleErrors.slice(0, 8).forEach((e) => console.log("console error:", String(e).slice(0, 200)));
ws.close(); edge.kill(); server.close();
process.exit(failures ? 1 : 0);
