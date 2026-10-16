#!/usr/bin/env node
// Dev-only (not deployed). Compares docs/translations/<lang>.json with en.json.
// Reports: missing keys, extra keys, changed {placeholders}, any digit other
// than 0-9, any currency sign other than the rupee sign.
// Run with: node scripts/check_translations.js [lang ...]   (default: every <lang>.json except en)
import { readFileSync, readdirSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "docs", "translations");
const load = (name) => JSON.parse(readFileSync(path.join(dir, `${name}.json`), "utf8"));
const placeholders = (s) => (String(s).match(/\{[^{}]*\}/g) || []).sort();

const langs = process.argv.slice(2).length
  ? process.argv.slice(2).map((l) => l.replace(/\.json$/, ""))
  : readdirSync(dir).filter((f) => f.endsWith(".json") && f !== "en.json").map((f) => f.replace(/\.json$/, ""));

if (!langs.length) {
  console.log("No translation files found next to en.json. Nothing to check.");
  process.exit(0);
}

const en = load("en");
let failed = false;

for (const lang of langs) {
  const tr = load(lang);
  const problems = [];
  for (const k of Object.keys(en)) {
    if (!(k in tr)) { problems.push(`missing key: ${k}`); continue; }
    if (typeof tr[k] !== "string" || tr[k].trim() === "") { problems.push(`empty or non-text value: ${k}`); continue; }
    const a = placeholders(en[k]).join(" ");
    const b = placeholders(tr[k]).join(" ");
    if (a !== b) problems.push(`changed placeholders: ${k} (English: ${a || "none"}; ${lang}: ${b || "none"})`);
  }
  for (const k of Object.keys(tr)) {
    if (!(k in en)) problems.push(`extra key: ${k}`);
  }
  for (const [k, v] of Object.entries(tr)) {
    if (typeof v !== "string") continue;
    const digits = [...v].filter((ch) => /\p{Nd}/u.test(ch) && !/[0-9]/.test(ch));
    if (digits.length) problems.push(`digit other than 0-9 in ${k}: ${[...new Set(digits)].join(" ")}`);
    const money = [...v].filter((ch) => /\p{Sc}/u.test(ch) && ch !== "\u20B9");
    if (money.length) problems.push(`currency sign other than the rupee sign in ${k}: ${[...new Set(money)].join(" ")}`);
  }
  if (problems.length) {
    failed = true;
    console.log(`${lang}.json: ${problems.length} problem(s)`);
    problems.forEach((p) => console.log(`  - ${p}`));
  } else {
    console.log(`${lang}.json: OK (${Object.keys(en).length} keys)`);
  }
}
process.exit(failed ? 1 : 0);
