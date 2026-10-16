#!/usr/bin/env node
// Dev-only (not deployed). Fails if a user-visible string is hard-coded in
// frontend/*.js, frontend/samples/*.js or frontend/index.html instead of coming
// from a translation key, and checks that the keys the code uses exist.
//
// What counts as user-visible text:
//   JS    - the right-hand side of .textContent / .innerText / .innerHTML /
//           .placeholder / .title / .alt / .ariaLabel, the value argument of
//           setAttribute("aria-label" | "alt" | "title" | "placeholder", ...),
//           arguments of showToast / alert / confirm / setLoading / new ApiError,
//           and object properties named label / description / message / text /
//           heading / caption, when they hold a string literal containing a letter.
//   HTML  - any text between tags and any aria-label / alt / title / placeholder
//           value that contains a letter (script and style blocks are scanned as JS
//           or ignored). Elements are expected to be empty and filled from keys.
// A string with no letter in it (for example "—", "?", "", "₹") is not text.
// A line carrying "i18n-ignore" is skipped; say why in the same comment.
//
// Also checks: every key used in the code is in frontend/lang/en.json; the five
// language files in frontend/lang are identical to docs/translations; and
// frontend/lang/en.json keeps every docs/translations/en.json key unchanged.
//
// Run with: node scripts/check_hardcoded_strings.js [rootDir]   (default: repo root)
import { existsSync, readFileSync, readdirSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(process.argv[2] || path.join(here, ".."));
const frontend = path.join(root, "frontend");
const problems = [];
const usedKeys = new Map(); // key -> "file:line"

const hasLetter = (s) => /\p{L}/u.test(s);

function recordKeys(text, where) {
  for (const m of text.matchAll(/["'`]((?:app|landing|upload|review|steps|nav|results|ask|evidence|rejected|costs|common|errors|splash|lang|samples|voice)\.[A-Za-z0-9.]+)["'`]/g)) {
    if (!usedKeys.has(m[1])) usedKeys.set(m[1], where);
  }
}

// Literals left in `rhs` after dropping ${...} expressions and t("key") calls.
function textLiterals(rhs) {
  const cleaned = rhs
    .replace(/\$\{[^}]*\}/g, "")
    .replace(/\bt\(\s*(["'`])[^"'`]*\1/g, "t(");
  return [...cleaned.matchAll(/"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g)]
    .map((m) => m[1] ?? m[2] ?? m[3])
    .filter(hasLetter);
}

const SINK_ASSIGN = /\.(?:textContent|innerText|innerHTML|placeholder|title|alt|ariaLabel)\s*=(?!=)\s*(.+)$/;
const SINK_ATTR = /setAttribute\(\s*["'](?:aria-label|alt|title|placeholder)["']\s*,(.+)$/;
const SINK_CALL = /\b(?:showToast|alert|confirm|setLoading)\((.+)$|new ApiError\((.+)$/;
const SINK_PROP = /\b(?:label|description|message|text|heading|caption)\s*:\s*(["'`].*)$/;

function scanJs(text, file, firstLine = 1) {
  text.split("\n").forEach((line, i) => {
    const where = `${file}:${firstLine + i}`;
    recordKeys(line, where);
    if (/i18n-ignore/.test(line) || /^\s*(\/\/|\*|\/\*)/.test(line)) return;
    for (const re of [SINK_ASSIGN, SINK_ATTR, SINK_CALL, SINK_PROP]) {
      const m = line.match(re);
      if (!m) continue;
      const found = textLiterals(m[1] ?? m[2] ?? "");
      if (found.length) {
        problems.push(`${where}: hard-coded text ${found.map((f) => JSON.stringify(f)).join(", ")}`);
        return;
      }
    }
  });
}

function scanHtml(text, file) {
  const lineOf = (index) => text.slice(0, index).split("\n").length;
  // Inline scripts are scanned as JS, then blanked so their code is not read as text.
  let body = text.replace(/<script\b[^>]*>([\s\S]*?)<\/script>/gi, (all, code, offset) => {
    scanJs(code, file, lineOf(offset + all.indexOf(code)));
    return all.replace(/[^\n]/g, " ");
  });
  body = body.replace(/<style\b[\s\S]*?<\/style>/gi, (all) => all.replace(/[^\n]/g, " "));
  body = body.replace(/<!--[\s\S]*?-->/g, (all) => all.replace(/[^\n]/g, " "));

  for (const m of body.matchAll(/<[a-zA-Z][^>]*>/g)) {
    const tag = m[0];
    const where = `${file}:${lineOf(m.index)}`;
    recordKeys(tag, where);
    for (const a of tag.matchAll(/(?<![\w-])(aria-label|alt|title|placeholder)="([^"]*)"/g)) {
      if (hasLetter(a[2])) problems.push(`${where}: hard-coded ${a[1]}="${a[2]}"`);
    }
  }
  const textOnly = body.replace(/<[^>]*>/g, (tag) => tag.replace(/[^\n]/g, "\0"));
  for (const m of textOnly.matchAll(/[^\0\n]+/g)) {
    const visible = m[0].replace(/&[#\w]+;/g, "").trim();
    if (visible && hasLetter(visible)) {
      problems.push(`${file}:${lineOf(m.index)}: hard-coded text "${visible}"`);
    }
  }
}

const jsFiles = [
  ...readdirSync(frontend).filter((f) => f.endsWith(".js")).map((f) => path.join(frontend, f)),
  ...(existsSync(path.join(frontend, "samples")) ? readdirSync(path.join(frontend, "samples")).filter((f) => f.endsWith(".js")).map((f) => path.join(frontend, "samples", f)) : []),
];
for (const file of jsFiles) {
  scanJs(readFileSync(file, "utf8"), path.relative(root, file).replace(/\\/g, "/"));
}
scanHtml(readFileSync(path.join(frontend, "index.html"), "utf8"), "frontend/index.html");

// --- keys and language files ------------------------------------------------
const langDir = path.join(frontend, "lang");
const docsDir = path.join(root, "docs", "translations");
const notes = [];
if (existsSync(langDir)) {
  const en = JSON.parse(readFileSync(path.join(langDir, "en.json"), "utf8"));
  for (const n of [1, 2, 3]) {
    usedKeys.set(`ask.suggestionsTrip.${n}`, "frontend/app.js (built from a prefix)");
    usedKeys.set(`ask.suggestionsWeekly.${n}`, "frontend/app.js (built from a prefix)");
  }
  for (const [key, where] of usedKeys) {
    const isPrefix = Object.keys(en).some((k) => k.startsWith(`${key}.`)); // e.g. "ask.suggestionsTrip" + ".1"
    if (!(key in en) && !isPrefix) problems.push(`${where}: key "${key}" is not in frontend/lang/en.json`);
  }
  const unused = Object.keys(en).filter((k) => !usedKeys.has(k));
  if (unused.length) notes.push(`keys in en.json that no code uses (informational): ${unused.join(", ")}`);

  if (existsSync(path.join(docsDir, "en.json"))) {
    const docsEn = JSON.parse(readFileSync(path.join(docsDir, "en.json"), "utf8"));
    for (const [k, v] of Object.entries(docsEn)) {
      if (en[k] !== v) problems.push(`frontend/lang/en.json: "${k}" differs from docs/translations/en.json`);
    }
    for (const lang of ["hi", "ta", "te", "kn", "ml"]) {
      const a = path.join(langDir, `${lang}.json`);
      const b = path.join(docsDir, `${lang}.json`);
      if (!existsSync(a)) problems.push(`frontend/lang/${lang}.json is missing`);
      else if (existsSync(b) && readFileSync(a, "utf8") !== readFileSync(b, "utf8")) {
        problems.push(`frontend/lang/${lang}.json differs from docs/translations/${lang}.json`);
      }
    }
  }
} else {
  notes.push("no frontend/lang directory here: key and language-file checks skipped");
}

console.log(`Scanned ${jsFiles.length} JS files and index.html under ${path.relative(process.cwd(), frontend) || "frontend"}; ${usedKeys.size} distinct keys used.`);
notes.forEach((n) => console.log(`note: ${n}`));
if (problems.length) {
  console.log(`FAIL -- ${problems.length} problem(s):`);
  problems.forEach((p) => console.log(`  - ${p}`));
  process.exit(1);
}
console.log("PASS -- no hard-coded user-visible text; every key used exists; language files match docs/translations.");
