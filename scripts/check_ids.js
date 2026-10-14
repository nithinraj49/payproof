#!/usr/bin/env node
// Dev-only verification script (not deployed, not part of frontend/).
// Lists every element id and class-selector app.js references via
// getElementById/querySelector/querySelectorAll and confirms each exists in
// frontend/index.html literally, matches a literal id pattern for a known
// template-literal family (e.g. step-dot-${i}), or is understood to be
// created dynamically by app.js itself. Reports any id that is genuinely
// missing. Run with: node scripts/check_ids.js
const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const appJs = fs.readFileSync(path.join(repoRoot, "frontend", "app.js"), "utf8");
const indexHtml = fs.readFileSync(path.join(repoRoot, "frontend", "index.html"), "utf8");

const htmlIds = new Set();
for (const m of indexHtml.matchAll(/\bid="([a-zA-Z0-9_-]+)"/g)) {
  htmlIds.add(m[1]);
}
const htmlClasses = new Set();
for (const m of indexHtml.matchAll(/\bclass="([^"]+)"/g)) {
  m[1].split(/\s+/).forEach((c) => c && htmlClasses.add(c));
}
// Classes app.js assigns to elements it creates itself (e.g.
// `row.className = "deduction-row"`) never appear as a literal class="..."
// in index.html at all -- they only exist once JS runs. A querySelector()
// call targeting one of these is valid even though index.html never
// mentions it, so these count as a second, equally valid source.
for (const m of appJs.matchAll(/\.className\s*=\s*"([^"]+)"/g)) {
  m[1].split(/\s+/).forEach((c) => c && htmlClasses.add(c));
}

// Known template-literal id families app.js builds at runtime (numbered 1-4
// or 1-3), checked against the actual numbered ids in index.html instead of
// the literal template string.
const TEMPLATE_FAMILIES = [
  { pattern: /`step-dot-\$\{/, prefix: "step-dot-", range: [1, 4] },
  { pattern: /`step-line-\$\{/, prefix: "step-line-", range: [1, 3] },
  { pattern: /`step-label-\$\{/, prefix: "step-label-", range: [1, 4] },
  { pattern: /`nav-\$\{/, prefix: "nav-", suffixes: ["results", "ask", "evidence"] },
];

// Ids app.js creates itself (via document.createElement + .id = ...) rather
// than reading from index.html -- not expected to be in the static markup.
const DYNAMICALLY_CREATED_IDS = new Set();

function checkLiteralIds() {
  const missing = [];
  const re = /getElementById\("([a-zA-Z0-9_-]+)"\)/g;
  let m;
  while ((m = re.exec(appJs))) {
    const id = m[1];
    if (!htmlIds.has(id) && !DYNAMICALLY_CREATED_IDS.has(id)) {
      missing.push(id);
    }
  }
  return [...new Set(missing)];
}

function checkTemplateFamilies() {
  const results = [];
  for (const family of TEMPLATE_FAMILIES) {
    if (!family.pattern.test(appJs)) {
      continue;
    }
    if (family.suffixes) {
      for (const suffix of family.suffixes) {
        const id = `${family.prefix}${suffix}`;
        results.push({ id, found: htmlIds.has(id) });
      }
    } else {
      for (let i = family.range[0]; i <= family.range[1]; i += 1) {
        const id = `${family.prefix}${i}`;
        results.push({ id, found: htmlIds.has(id) });
      }
    }
  }
  return results;
}

function checkClassSelectors() {
  const missing = [];
  const re = /querySelector(?:All)?\("\.([a-zA-Z0-9_-]+)"\)/g;
  let m;
  while ((m = re.exec(appJs))) {
    const cls = m[1];
    if (!htmlClasses.has(cls)) {
      missing.push(cls);
    }
  }
  return [...new Set(missing)];
}

const missingLiteralIds = checkLiteralIds();
const templateResults = checkTemplateFamilies();
const missingTemplateIds = templateResults.filter((r) => !r.found);
const missingClasses = checkClassSelectors();

console.log(`Checked ${htmlIds.size} ids and ${htmlClasses.size} classes in frontend/index.html against frontend/app.js.\n`);

console.log(`Literal getElementById() ids: ${missingLiteralIds.length === 0 ? "all resolve" : "MISSING: " + missingLiteralIds.join(", ")}`);
console.log(`Template-literal id families checked individually (${templateResults.length} ids): ${missingTemplateIds.length === 0 ? "all resolve" : "MISSING: " + missingTemplateIds.map((r) => r.id).join(", ")}`);
console.log(`Class selectors (querySelector/All): ${missingClasses.length === 0 ? "all resolve" : "MISSING: " + missingClasses.join(", ")}`);

const anyMissing = missingLiteralIds.length > 0 || missingTemplateIds.length > 0 || missingClasses.length > 0;
console.log(`\n${anyMissing ? "FAIL -- see MISSING entries above" : "PASS -- every id/selector app.js uses exists in index.html (or is a known dynamic/template case)"}`);
process.exit(anyMissing ? 1 : 0);
