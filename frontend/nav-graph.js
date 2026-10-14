// Single source of truth for screen navigation (item 1, 14 Oct 2026), shared
// by frontend/app.js (real navigation) and scripts/check_nav_graph.js
// (dev-only verification, not deployed). Pure data, no DOM access, so both
// a browser and plain Node can import it unchanged.
export const ROOT_SCREEN = "landing";

// Explicit Back-button target for a screen, where one exists (item 1a).
// null means "no dedicated Back button on this screen" -- those screens
// still have the global header Home as their way out (item 1c), which the
// checker treats as satisfying "no dead end" on its own.
export const BACK_TARGETS = {
  landing: null,
  review: "landing",
  rejected: null, // has its own explicit "Try another screenshot" + Home instead
  costs: "review",
  results: "costs",
  ask: null, // reachable via the bottom nav bar; Home is this screen's way out
  evidence: null,
};

// Step indicator (Upload/Check/Costs/Results) -> the screen a tap on a
// *completed* step navigates to (item 1b). Only steps 1-4 are dots; ask/
// evidence share step 4 with results but are not step-dot targets.
export const STEP_TO_SCREEN = { 1: "landing", 2: "review", 3: "costs", 4: "results" };

export const ALL_SCREENS = Object.keys(BACK_TARGETS);
