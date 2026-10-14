#!/usr/bin/env node
// Dev-only verification script (not deployed, not part of frontend/).
// Walks the screen graph in frontend/nav-graph.js and checks every screen
// has a valid back target or is otherwise known to have an escape hatch
// (item 1f, 14 Oct 2026): the global header Home/brand (every screen), or
// the rejected screen's own explicit "Try another screenshot" + Home.
// Run with: node scripts/check_nav_graph.js
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";
import { ALL_SCREENS, BACK_TARGETS, ROOT_SCREEN, STEP_TO_SCREEN } from "../frontend/nav-graph.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const indexHtml = readFileSync(path.join(repoRoot, "frontend", "index.html"), "utf8");

const failures = [];

// 1. Every back target (if not null) must itself be a known screen.
for (const [screen, target] of Object.entries(BACK_TARGETS)) {
  if (target !== null && !ALL_SCREENS.includes(target)) {
    failures.push(`${screen}'s back target "${target}" is not a known screen`);
  }
}

// 2. Exactly one root screen (back target null AND it's the designated root).
if (BACK_TARGETS[ROOT_SCREEN] !== null) {
  failures.push(`ROOT_SCREEN "${ROOT_SCREEN}" must have a null back target`);
}

// 3. Every screen without a dedicated Back button must have the global
// header Home available -- true for every screen by construction (the
// header is outside the per-screen <section> markup), so just confirm the
// header's Home control actually exists in index.html once.
if (!/id="btn-home"/.test(indexHtml) || !/id="btn-brand-home"/.test(indexHtml)) {
  failures.push("global header Home/brand control is missing from index.html -- every screen relies on it as a fallback escape hatch");
}

// 4. The rejected screen's own explicit requirement: "Try another
// screenshot" AND Home, not just the global header.
if (!/id="btn-try-another"/.test(indexHtml)) {
  failures.push('rejected screen is missing "Try another screenshot" (#btn-try-another)');
}
if (!/id="btn-rejected-home"/.test(indexHtml)) {
  failures.push("rejected screen is missing its own Home control (#btn-rejected-home)");
}

// 5. Every screen referenced by BACK_TARGETS or STEP_TO_SCREEN must have a
// matching <section id="screen-...">.
for (const screen of ALL_SCREENS) {
  if (!new RegExp(`id="screen-${screen}"`).test(indexHtml)) {
    failures.push(`no <section id="screen-${screen}"> found in index.html`);
  }
}
for (const screen of Object.values(STEP_TO_SCREEN)) {
  if (!ALL_SCREENS.includes(screen)) {
    failures.push(`STEP_TO_SCREEN points to unknown screen "${screen}"`);
  }
}

// 6. Every screen with a dedicated Back button must have that button in
// index.html (id convention: btn-back-<screen>).
for (const [screen, target] of Object.entries(BACK_TARGETS)) {
  if (target !== null) {
    const id = `btn-back-${screen}`;
    if (!new RegExp(`id="${id}"`).test(indexHtml)) {
      failures.push(`${screen} has a back target but no #${id} button in index.html`);
    }
  }
}

console.log(`Checked ${ALL_SCREENS.length} screens: ${ALL_SCREENS.join(", ")}`);
console.log(`Root screen: ${ROOT_SCREEN}`);
console.log(`Step-to-screen map: ${JSON.stringify(STEP_TO_SCREEN)}`);
console.log();

if (failures.length > 0) {
  console.log(`FAIL -- ${failures.length} problem(s):`);
  failures.forEach((f) => console.log(`  - ${f}`));
  process.exit(1);
} else {
  console.log("PASS -- every screen has a valid back target or a known escape hatch (Home, or rejected's own controls); no dead ends found.");
}
