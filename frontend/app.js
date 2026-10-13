// Screen controller for PayProof's floor: landing -> review -> costs.
// Plain DOM manipulation, no framework, no build step (CLAUDE.md / REQUIREMENTS.md section 9).
import { api, ApiError } from "./api.js";
import { STRINGS } from "./strings.js";
import { SAMPLE_IMAGES } from "./samples/index.js";
import { currencySymbol, formatDateHuman, formatMoney, formatRate, formatPercent } from "./format.js";
import { createBarScene, SPLASH_DURATION } from "./brutalist-bars.js";

const SPLASH_SESSION_KEY = "payproof_splash_shown";

// Opening splash (item 4): plays once per browser session, skippable by tap
// or key, skipped entirely under prefers-reduced-motion or ?nosplash=1,
// never blocks sign-in or any API call (it's a plain fixed overlay drawn on
// top; everything underneath keeps loading and running regardless).
export function initSplash() {
  const splashEl = document.getElementById("splash");
  const params = new URLSearchParams(window.location.search);
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const alreadyShown = sessionStorage.getItem(SPLASH_SESSION_KEY) === "1";

  if (params.get("nosplash") === "1" || reduce || alreadyShown) {
    splashEl.remove();
    return;
  }

  sessionStorage.setItem(SPLASH_SESSION_KEY, "1");

  let done = false;
  function finish() {
    if (done) {
      return;
    }
    done = true;
    splashEl.classList.add("splash-hide");
    setTimeout(() => splashEl.remove(), 400);
  }

  try {
    const scene = createBarScene(document.getElementById("splash-svg"));
    splashEl.addEventListener("click", finish);
    window.addEventListener("keydown", function onKey() {
      finish();
      window.removeEventListener("keydown", onKey);
    });
    scene.play(finish);
  } catch (err) {
    // If the script fails for any reason, the app simply shows (no splash).
    console.error(err);
    finish();
  }
}

// Sample-mode defaults so a visitor never has to type anything except to
// change a prefilled value (CLAUDE.md step 2: "no typing except changing
// prefilled sample costs and hours").
const SAMPLE_DEFAULT_FUEL_PER_KM = 3;
const SAMPLE_DEFAULT_MAINTENANCE_PER_KM = 1;
const SAMPLE_DEFAULT_TRIP_HOURS_ONLINE = 1.5;
const SAMPLE_DEFAULT_WEEKLY_KM_DRIVEN = 300;
const SAMPLE_DEFAULT_WEEKLY_HOURS_ONLINE = 42;

let uidCounter = 0;
function uid(prefix) {
  uidCounter += 1;
  return `${prefix}-${uidCounter}`;
}

// ---------------------------------------------------------------------------
// App state
// ---------------------------------------------------------------------------

const state = {
  mode: null, // "trip" | "weekly" | null
  currency: "INR",
  tripGroups: [], // trip mode: [{ id, previewUrl, needsReview, notes, trips: [tripRow] }]
  weekGroup: null, // weekly mode: { id, previewUrl, needsReview, notes, periodLabel, creditedOn, lines, deductions, totalCredited, kmDriven, hoursOnline }
  rejectedInBatch: [], // [{ fileName, reason }]
  lastRejectedReason: null,
  loggedInHoursEntered: null,
  askAndEvidenceRendered: false,
  isSampleMode: false,
};

function resetState() {
  state.mode = null;
  state.currency = "INR";
  state.tripGroups = [];
  state.weekGroup = null;
  state.rejectedInBatch = [];
  state.lastRejectedReason = null;
  state.loggedInHoursEntered = null;
  state.askAndEvidenceRendered = false;
  state.isSampleMode = false;
}

function makeField(value, confirmed) {
  return { value: value === undefined ? null : value, confirmed: !!confirmed };
}

function initialConfirmed(value, fieldName, lowConfidenceFields, needsReview) {
  if (needsReview) return false;
  if (value === null || value === undefined || value === "") return false;
  if (lowConfidenceFields && lowConfidenceFields.includes(fieldName)) return false;
  return true;
}

// ---------------------------------------------------------------------------
// Low-level UI helpers
// ---------------------------------------------------------------------------

const screens = {
  landing: document.getElementById("screen-landing"),
  review: document.getElementById("screen-review"),
  rejected: document.getElementById("screen-rejected"),
  costs: document.getElementById("screen-costs"),
  results: document.getElementById("screen-results"),
  ask: document.getElementById("screen-ask"),
  evidence: document.getElementById("screen-evidence"),
};

const appNav = document.getElementById("app-nav");
const NAV_SCREENS = ["results", "ask", "evidence"];

// Step indicator: Upload, Check, Costs, Results (item 4). Rejected is a
// dead-end off the happy path, so the indicator hides there rather than
// claiming a step that didn't complete.
const SCREEN_TO_STEP = { landing: 1, review: 2, rejected: null, costs: 3, results: 4, ask: 4, evidence: 4 };
const stepIndicatorEl = document.getElementById("step-indicator");

function setStep(stepNumber) {
  if (stepNumber === null || stepNumber === undefined) {
    stepIndicatorEl.hidden = true;
    return;
  }
  stepIndicatorEl.hidden = false;
  for (let i = 1; i <= 4; i += 1) {
    const dot = document.getElementById(`step-dot-${i}`);
    dot.classList.toggle("active", i === stepNumber);
    dot.classList.toggle("done", i < stepNumber);
  }
  for (let i = 1; i <= 3; i += 1) {
    document.getElementById(`step-line-${i}`).classList.toggle("filled", i < stepNumber);
  }
}

function showScreen(name) {
  for (const key of Object.keys(screens)) {
    screens[key].hidden = key !== name;
  }
  if (NAV_SCREENS.includes(name)) {
    appNav.hidden = false;
    NAV_SCREENS.forEach((key) => {
      document.getElementById(`nav-${key}`).classList.toggle("active", key === name);
    });
  } else {
    appNav.hidden = true;
  }
  setStep(SCREEN_TO_STEP[name]);
  window.scrollTo(0, 0);
}

function setupNav() {
  document.getElementById("nav-results").textContent = STRINGS.nav.results;
  document.getElementById("nav-ask").textContent = STRINGS.nav.ask;
  document.getElementById("nav-evidence").textContent = STRINGS.nav.evidence;
  document.getElementById("nav-results").addEventListener("click", () => {
    showScreen("results");
    fetchAndShowResults();
  });
  document.getElementById("nav-ask").addEventListener("click", () => {
    showScreen("ask");
  });
  document.getElementById("nav-evidence").addEventListener("click", () => {
    showScreen("evidence");
  });
}

// ---------------------------------------------------------------------------
// Screenshot preview lightbox (tap to enlarge; the thumbnail itself is
// capped to ~40% of viewport height so the review table stays reachable
// without a long scroll on a phone).
// ---------------------------------------------------------------------------

const lightboxEl = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");

function openLightbox(url) {
  lightboxImg.src = url;
  lightboxEl.hidden = false;
}

function setupLightbox() {
  lightboxEl.addEventListener("click", () => {
    lightboxEl.hidden = true;
  });
}

function createPreviewImage(url) {
  const fragment = document.createDocumentFragment();
  const img = document.createElement("img");
  img.className = "preview";
  img.src = url;
  img.alt = "Your uploaded screenshot";
  img.addEventListener("click", () => openLightbox(url));
  fragment.appendChild(img);

  const hint = document.createElement("p");
  hint.className = "preview-hint";
  hint.textContent = STRINGS.review.tapToEnlarge;
  fragment.appendChild(hint);

  return fragment;
}

const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");

function setLoading(isLoading, text) {
  loadingOverlay.hidden = !isLoading;
  loadingText.textContent = text || STRINGS.common.loading;
}

const toastEl = document.getElementById("toast");
let toastTimer = null;

function showToast(message) {
  toastEl.textContent = message;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, 5000);
}

function describeError(err) {
  if (err instanceof ApiError) {
    return err.message;
  }
  console.error(err);
  return STRINGS.errors.generic;
}

// A small, persistent, plain-text technical line (status + error_code, no
// user data or secrets) alongside the friendly toast, so a failed call is
// never silent about exactly what failed (CLAUDE.md step 4).
const errorLineEl = document.getElementById("error-line");

function setupErrorLine() {
  errorLineEl.addEventListener("click", () => {
    errorLineEl.hidden = true;
  });
}

function showApiError(err) {
  showToast(describeError(err));
  if (err instanceof ApiError) {
    errorLineEl.textContent = STRINGS.errors.technicalLine(err.status, err.code);
    errorLineEl.hidden = false;
  }
}

function clearChildren(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

// ---------------------------------------------------------------------------
// Screen a: landing
// ---------------------------------------------------------------------------

function renderLandingStrings() {
  document.getElementById("landing-headline").textContent = STRINGS.landing.headline;
  document.getElementById("landing-tagline").textContent = STRINGS.landing.tagline;
  document.getElementById("btn-try-sample").textContent = STRINGS.landing.trySample;
  document.getElementById("sample-simulated-note").textContent = STRINGS.landing.simulatedNote;
  document.getElementById("upload-heading").textContent = STRINGS.landing.upload;
  document.getElementById("how-it-works-1").textContent = STRINGS.landing.howItWorks1;
  document.getElementById("how-it-works-2").textContent = STRINGS.landing.howItWorks2;
  document.getElementById("how-it-works-3").textContent = STRINGS.landing.howItWorks3;
  document.getElementById("landing-privacy").textContent = STRINGS.landing.privacyNote;

  const heroScene = createBarScene(document.getElementById("landing-hero-svg"));
  heroScene.render(SPLASH_DURATION); // static final frame, no animation (item 5)
}

function setupLanding() {
  const sampleBtn = document.getElementById("btn-try-sample");
  const samplePicker = document.getElementById("sample-picker");
  sampleBtn.addEventListener("click", () => {
    samplePicker.hidden = !samplePicker.hidden;
  });

  const cardsEl = document.getElementById("sample-cards");
  SAMPLE_IMAGES.forEach((sample) => {
    const card = document.createElement("div");
    card.className = "sample-card tilt-card";

    const h4 = document.createElement("h4");
    h4.textContent = sample.label;
    card.appendChild(h4);

    const p = document.createElement("p");
    p.textContent = sample.description;
    card.appendChild(p);

    const useBtn = document.createElement("button");
    useBtn.type = "button";
    useBtn.className = "secondary";
    useBtn.textContent = STRINGS.landing.useThisSample;
    useBtn.addEventListener("click", () => handleUseSample(sample));
    card.appendChild(useBtn);

    cardsEl.appendChild(card);
  });

  const fileInput = document.getElementById("file-input");
  fileInput.addEventListener("change", async () => {
    const files = Array.from(fileInput.files || []);
    if (files.length === 0) {
      showToast(STRINGS.upload.noFileChosen);
      return;
    }
    await handleUpload(files, false);
    fileInput.value = "";
  });
}

async function handleUseSample(sample) {
  try {
    setLoading(true, STRINGS.common.loading);
    const response = await fetch(sample.url);
    if (!response.ok) {
      throw new Error(`Could not load ${sample.url}`);
    }
    const blob = await response.blob();
    const file = new File([blob], sample.fileName, { type: blob.type || "image/jpeg" });
    await handleUpload([file], true);
  } catch (err) {
    setLoading(false);
    showToast(describeError(err));
  }
}

// ---------------------------------------------------------------------------
// Upload + extraction
// ---------------------------------------------------------------------------

async function handleUpload(files, isSample) {
  resetState();
  state.isSampleMode = !!isSample;

  for (let i = 0; i < files.length; i += 1) {
    const file = files[i];
    setLoading(true, STRINGS.upload.processing(i + 1, files.length));

    let result;
    try {
      result = await api.extract(file, state.isSampleMode);
    } catch (err) {
      state.rejectedInBatch.push({ fileName: file.name, reason: describeError(err) });
      continue;
    }

    if (result.currency) {
      state.currency = result.currency;
    }

    if (result.screen_type === "order_offer" || result.screen_type === "other") {
      state.rejectedInBatch.push({
        fileName: file.name,
        reason: result.notes || STRINGS.rejected.genericReason,
      });
      continue;
    }

    if (result.screen_type === "trip_detail" || result.screen_type === "trip_list") {
      if (state.mode === "weekly") {
        state.rejectedInBatch.push({ fileName: file.name, reason: STRINGS.upload.modeMismatch });
        continue;
      }
      state.mode = "trip";
      addTripGroup(file, result);
      continue;
    }

    if (result.screen_type === "payout_summary") {
      if (state.mode === "trip") {
        state.rejectedInBatch.push({ fileName: file.name, reason: STRINGS.upload.modeMismatch });
        continue;
      }
      state.mode = "weekly";
      setWeekGroup(file, result);
      continue;
    }

    // Defensive fallback: an unrecognised screen_type is treated as rejected,
    // never silently shown as data (REQUIREMENTS.md "no guessing").
    state.rejectedInBatch.push({ fileName: file.name, reason: STRINGS.rejected.genericReason });
  }

  setLoading(false);

  const hasTrips = state.tripGroups.some((g) => g.trips.length > 0);
  const hasWeek = state.weekGroup !== null;

  if (!hasTrips && !hasWeek) {
    const reason = state.rejectedInBatch.length > 0
      ? state.rejectedInBatch[state.rejectedInBatch.length - 1].reason
      : STRINGS.rejected.genericReason;
    renderRejected(reason);
    showScreen("rejected");
    return;
  }

  renderReview();
  showScreen("review");
}

function addTripGroup(file, result) {
  const previewUrl = URL.createObjectURL(file);
  const group = {
    id: uid("group"),
    previewUrl,
    needsReview: !!result.needs_review,
    notes: result.notes || null,
    trips: (result.trips || []).map((t) => tripFromExtraction(t, !!result.needs_review)),
  };
  state.tripGroups.push(group);
}

function tripFromExtraction(trip, needsReview) {
  const low = trip.low_confidence_fields || [];
  return {
    id: uid("trip"),
    orderId: trip.order_id || null,
    orderType: trip.order_type || null,
    date: makeField(trip.trip_date, false), // dates always need an explicit tap
    basePay: makeField(trip.base_pay, initialConfirmed(trip.base_pay, "base_pay", low, needsReview)),
    incentive: makeField(trip.incentive, initialConfirmed(trip.incentive, "incentive", low, needsReview)),
    tip: makeField(trip.tip, initialConfirmed(trip.tip, "tip", low, needsReview)),
    totalPayout: makeField(trip.total_payout, initialConfirmed(trip.total_payout, "total_payout", low, needsReview)),
    distanceKm: makeField(trip.distance_km, initialConfirmed(trip.distance_km, "distance_km", low, needsReview)),
    durationMin: makeField(trip.duration_min, initialConfirmed(trip.duration_min, "duration_min", low, needsReview)),
    deductions: {
      items: (trip.deductions || []).map((d) => ({ label: d.label, amount: d.amount })),
      confirmed: !needsReview,
    },
  };
}

function blankTripRow() {
  return {
    id: uid("trip"),
    orderId: null,
    orderType: null,
    date: makeField(null, false),
    basePay: makeField(null, true),
    incentive: makeField(null, true),
    tip: makeField(null, true),
    totalPayout: makeField(null, true),
    distanceKm: makeField(null, true),
    durationMin: makeField(null, true),
    deductions: { items: [], confirmed: true },
  };
}

function setWeekGroup(file, result) {
  const previewUrl = URL.createObjectURL(file);
  const summary = result.payout_summary || {};
  const low = summary.low_confidence_fields || [];
  const needsReview = !!result.needs_review;
  state.weekGroup = {
    id: uid("week"),
    previewUrl,
    needsReview,
    notes: result.notes || null,
    periodLabel: makeField(summary.period_label, initialConfirmed(summary.period_label, "period_label", low, needsReview)),
    creditedOn: summary.credited_on || null,
    lines: {
      items: (summary.lines || []).map((l) => ({ label: l.label, amount: l.amount })),
      confirmed: !needsReview,
    },
    deductions: {
      items: (summary.deductions || []).map((d) => ({ label: d.label, amount: d.amount })),
      confirmed: !needsReview,
    },
    totalCredited: makeField(summary.total_credited, initialConfirmed(summary.total_credited, "total_credited", low, needsReview)),
    // Worker-entered, never extracted (REQUIREMENTS.md 5.2) -- prefilled with
    // a plausible default in sample mode so there's nothing to type, per
    // CLAUDE.md step 2.
    kmDriven: state.isSampleMode ? SAMPLE_DEFAULT_WEEKLY_KM_DRIVEN : null,
    hoursOnline: state.isSampleMode ? SAMPLE_DEFAULT_WEEKLY_HOURS_ONLINE : null,
  };
}

// ---------------------------------------------------------------------------
// Screen b: review (shared field-rendering helpers)
// ---------------------------------------------------------------------------

function createNumberField(labelText, fieldState, onChanged) {
  const wrap = document.createElement("div");
  wrap.className = "field";

  const label = document.createElement("label");
  label.textContent = labelText;
  wrap.appendChild(label);

  const row = document.createElement("div");
  row.className = "field-row";

  const input = document.createElement("input");
  input.type = "number";
  input.step = "0.01";
  input.min = "0";
  input.inputMode = "decimal";
  if (fieldState.value !== null && fieldState.value !== undefined) {
    input.value = fieldState.value;
  }

  const confirmBtn = document.createElement("button");
  confirmBtn.type = "button";
  confirmBtn.className = "small confirm-btn";

  function refresh() {
    wrap.classList.toggle("unconfirmed", !fieldState.confirmed);
    confirmBtn.textContent = fieldState.confirmed ? STRINGS.review.confirmed : STRINGS.review.confirm;
    confirmBtn.classList.toggle("is-confirmed", fieldState.confirmed);
  }

  input.addEventListener("input", () => {
    const raw = input.value;
    fieldState.value = raw === "" ? null : Number(raw);
    fieldState.confirmed = raw !== "";
    refresh();
    onChanged();
  });

  confirmBtn.addEventListener("click", () => {
    if (fieldState.value === null || fieldState.value === undefined) {
      return; // nothing to confirm if the cell is still blank
    }
    fieldState.confirmed = !fieldState.confirmed;
    refresh();
    onChanged();
  });

  refresh();
  row.appendChild(input);
  row.appendChild(confirmBtn);
  wrap.appendChild(row);

  if (fieldState.value === null || fieldState.value === undefined) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = STRINGS.review.blankFieldHint;
    wrap.appendChild(hint);
  }

  return wrap;
}

function createDateField(fieldState, onChanged) {
  const wrap = document.createElement("div");
  wrap.className = "field";

  const label = document.createElement("label");
  label.textContent = STRINGS.review.date;
  wrap.appendChild(label);

  const row = document.createElement("div");
  row.className = "field-row";

  const input = document.createElement("input");
  input.type = "date";
  if (fieldState.value) {
    input.value = fieldState.value;
  }

  const confirmBtn = document.createElement("button");
  confirmBtn.type = "button";
  confirmBtn.className = "small confirm-btn";

  const humanDate = document.createElement("span");
  humanDate.className = "date-human";

  function refresh() {
    wrap.classList.toggle("unconfirmed", !fieldState.confirmed);
    confirmBtn.textContent = fieldState.confirmed ? STRINGS.review.dateConfirmed : STRINGS.review.confirmDate;
    confirmBtn.classList.toggle("is-confirmed", fieldState.confirmed);
    const human = formatDateHuman(fieldState.value);
    humanDate.textContent = human || "";
  }

  input.addEventListener("input", () => {
    fieldState.value = input.value || null;
    fieldState.confirmed = false; // editing a date always requires a fresh explicit confirm
    refresh();
    onChanged();
  });

  confirmBtn.addEventListener("click", () => {
    if (!fieldState.value) {
      return;
    }
    fieldState.confirmed = !fieldState.confirmed;
    refresh();
    onChanged();
  });

  refresh();
  row.appendChild(input);
  row.appendChild(confirmBtn);
  wrap.appendChild(row);
  wrap.appendChild(humanDate);
  return wrap;
}

function createAmountListField(titleText, listState, labelHint, amountHint, addText, onChanged) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  wrap.dataset.role = "amount-list";

  const label = document.createElement("label");
  label.textContent = titleText;
  wrap.appendChild(label);

  const rowsContainer = document.createElement("div");
  wrap.appendChild(rowsContainer);

  function renderRows() {
    clearChildren(rowsContainer);
    listState.items.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "deduction-row";

      const labelField = document.createElement("div");
      labelField.className = "field";
      const labelInput = document.createElement("input");
      labelInput.type = "text";
      labelInput.placeholder = labelHint;
      labelInput.value = item.label || "";
      labelInput.addEventListener("input", () => {
        item.label = labelInput.value;
        onChanged();
      });
      labelField.appendChild(labelInput);

      const amountField = document.createElement("div");
      amountField.className = "field";
      const amountInput = document.createElement("input");
      amountInput.type = "number";
      amountInput.min = "0";
      amountInput.step = "0.01";
      amountInput.placeholder = amountHint;
      amountInput.value = item.amount === null || item.amount === undefined ? "" : item.amount;
      amountInput.addEventListener("input", () => {
        item.amount = amountInput.value === "" ? 0 : Number(amountInput.value);
        onChanged();
      });
      amountField.appendChild(amountInput);

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "small";
      removeBtn.textContent = STRINGS.review.removeDeduction;
      removeBtn.addEventListener("click", () => {
        listState.items.splice(index, 1);
        renderRows();
        onChanged();
      });

      row.appendChild(labelField);
      row.appendChild(amountField);
      row.appendChild(removeBtn);
      rowsContainer.appendChild(row);
    });
  }

  renderRows();

  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "small";
  addBtn.textContent = addText;
  addBtn.addEventListener("click", () => {
    listState.items.push({ label: "", amount: 0 });
    listState.confirmed = true; // the worker is directly entering this row
    renderRows();
    onChanged();
  });
  wrap.appendChild(addBtn);

  if (!listState.confirmed) {
    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "small confirm-btn";
    function refreshConfirm() {
      wrap.classList.toggle("unconfirmed", !listState.confirmed);
      confirmBtn.textContent = listState.confirmed ? STRINGS.review.confirmed : STRINGS.review.confirm;
      confirmBtn.classList.toggle("is-confirmed", listState.confirmed);
    }
    confirmBtn.addEventListener("click", () => {
      listState.confirmed = !listState.confirmed;
      refreshConfirm();
      onChanged();
    });
    refreshConfirm();
    wrap.appendChild(confirmBtn);
  }

  return wrap;
}

function moneyLabel(base) {
  return `${base} (${currencySymbol(state.currency)})`;
}

function renderTripCard(group, trip, onChanged) {
  const card = document.createElement("div");
  card.className = "card";

  const h3 = document.createElement("h3");
  h3.textContent = STRINGS.review.tripCardTitle;
  card.appendChild(h3);

  if (trip.orderId) {
    const p = document.createElement("p");
    p.className = "readonly-note";
    p.textContent = `${STRINGS.review.orderId}: ${trip.orderId}`;
    card.appendChild(p);
  }
  if (trip.orderType) {
    const p = document.createElement("p");
    p.className = "readonly-note";
    p.textContent = `${STRINGS.review.orderType}: ${trip.orderType}`;
    card.appendChild(p);
  }

  card.appendChild(createDateField(trip.date, onChanged));
  card.appendChild(createNumberField(moneyLabel(STRINGS.review.basePay), trip.basePay, onChanged));
  card.appendChild(createNumberField(moneyLabel(STRINGS.review.incentive), trip.incentive, onChanged));
  card.appendChild(createNumberField(moneyLabel(STRINGS.review.tip), trip.tip, onChanged));
  card.appendChild(createNumberField(moneyLabel(STRINGS.review.totalPayout), trip.totalPayout, onChanged));
  card.appendChild(createNumberField(STRINGS.review.distanceKm, trip.distanceKm, onChanged));
  card.appendChild(createNumberField(STRINGS.review.durationMin, trip.durationMin, onChanged));
  card.appendChild(createAmountListField(
    moneyLabel(STRINGS.review.deductions),
    trip.deductions,
    STRINGS.review.deductionLabel,
    STRINGS.review.deductionAmount,
    STRINGS.review.addDeduction,
    onChanged,
  ));

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "small";
  removeBtn.textContent = STRINGS.review.removeTrip;
  removeBtn.addEventListener("click", () => {
    group.trips = group.trips.filter((t) => t.id !== trip.id);
    renderReview();
  });
  card.appendChild(removeBtn);

  return card;
}

function renderReview() {
  document.getElementById("review-title").textContent = STRINGS.review.title;

  const rejectedBlock = document.getElementById("review-rejected-in-batch");
  const rejectedList = document.getElementById("review-rejected-list");
  clearChildren(rejectedList);
  if (state.rejectedInBatch.length > 0) {
    document.getElementById("review-rejected-in-batch-label").textContent = STRINGS.review.rejectedInBatch;
    state.rejectedInBatch.forEach((r) => {
      const li = document.createElement("li");
      li.textContent = `${r.fileName}: ${r.reason}`;
      rejectedList.appendChild(li);
    });
    rejectedBlock.hidden = false;
  } else {
    rejectedBlock.hidden = true;
  }

  const groupsEl = document.getElementById("review-groups");
  clearChildren(groupsEl);

  const onChanged = () => updateContinueButtonState();

  if (state.mode === "trip") {
    state.tripGroups.forEach((group) => {
      if (group.trips.length === 0) {
        return;
      }
      const block = document.createElement("div");

      if (group.previewUrl) {
        block.appendChild(createPreviewImage(group.previewUrl));
      }

      if (group.needsReview) {
        const banner = document.createElement("div");
        banner.className = "banner";
        banner.textContent = STRINGS.review.needsReviewBanner;
        block.appendChild(banner);
      }

      group.trips.forEach((trip) => {
        block.appendChild(renderTripCard(group, trip, onChanged));
      });

      groupsEl.appendChild(block);
    });

    const addTripBtn = document.createElement("button");
    addTripBtn.type = "button";
    addTripBtn.className = "secondary";
    addTripBtn.textContent = STRINGS.review.addTrip;
    addTripBtn.addEventListener("click", () => {
      if (state.tripGroups.length === 0 || state.tripGroups[state.tripGroups.length - 1].manual !== true) {
        state.tripGroups.push({ id: uid("group"), previewUrl: null, needsReview: false, notes: null, trips: [], manual: true });
      }
      state.tripGroups[state.tripGroups.length - 1].trips.push(blankTripRow());
      renderReview();
    });
    groupsEl.appendChild(addTripBtn);
  } else if (state.mode === "weekly") {
    const group = state.weekGroup;
    const block = document.createElement("div");
    const card = document.createElement("div");
    card.className = "card";

    const h3 = document.createElement("h3");
    h3.textContent = STRINGS.review.weeklyCardTitle;
    card.appendChild(h3);

    if (group.previewUrl) {
      card.appendChild(createPreviewImage(group.previewUrl));
    }

    if (group.needsReview) {
      const banner = document.createElement("div");
      banner.className = "banner";
      banner.textContent = STRINGS.review.needsReviewBanner;
      card.appendChild(banner);
    }

    const periodField = document.createElement("div");
    periodField.className = "field";
    const periodLabelEl = document.createElement("label");
    periodLabelEl.textContent = STRINGS.review.periodLabel;
    periodField.appendChild(periodLabelEl);
    const periodRow = document.createElement("div");
    periodRow.className = "field-row";
    const periodInput = document.createElement("input");
    periodInput.type = "text";
    periodInput.value = group.periodLabel.value || "";
    const periodConfirmBtn = document.createElement("button");
    periodConfirmBtn.type = "button";
    periodConfirmBtn.className = "small confirm-btn";
    function refreshPeriod() {
      periodField.classList.toggle("unconfirmed", !group.periodLabel.confirmed);
      periodConfirmBtn.textContent = group.periodLabel.confirmed ? STRINGS.review.confirmed : STRINGS.review.confirm;
      periodConfirmBtn.classList.toggle("is-confirmed", group.periodLabel.confirmed);
    }
    periodInput.addEventListener("input", () => {
      group.periodLabel.value = periodInput.value || null;
      group.periodLabel.confirmed = periodInput.value !== "";
      refreshPeriod();
      onChanged();
    });
    periodConfirmBtn.addEventListener("click", () => {
      if (!group.periodLabel.value) return;
      group.periodLabel.confirmed = !group.periodLabel.confirmed;
      refreshPeriod();
      onChanged();
    });
    refreshPeriod();
    periodRow.appendChild(periodInput);
    periodRow.appendChild(periodConfirmBtn);
    periodField.appendChild(periodRow);
    card.appendChild(periodField);

    if (group.creditedOn) {
      const p = document.createElement("p");
      p.className = "readonly-note";
      const human = formatDateHuman(group.creditedOn);
      p.textContent = `${STRINGS.review.creditedOn}: ${group.creditedOn}${human ? ` (${human})` : ""}`;
      card.appendChild(p);
    }

    card.appendChild(createAmountListField(
      moneyLabel(STRINGS.review.lines), group.lines, STRINGS.review.lineLabel, STRINGS.review.lineAmount, STRINGS.review.addLine, onChanged,
    ));
    card.appendChild(createAmountListField(
      moneyLabel(STRINGS.review.deductions), group.deductions, STRINGS.review.deductionLabel, STRINGS.review.deductionAmount, STRINGS.review.addDeduction, onChanged,
    ));
    card.appendChild(createNumberField(moneyLabel(STRINGS.review.totalCredited), group.totalCredited, onChanged));

    const kmField = document.createElement("div");
    kmField.className = "field";
    const kmLabel = document.createElement("label");
    kmLabel.textContent = STRINGS.review.kmDriven;
    kmField.appendChild(kmLabel);
    const kmInput = document.createElement("input");
    kmInput.type = "number";
    kmInput.min = "0";
    kmInput.step = "0.01";
    if (group.kmDriven !== null && group.kmDriven !== undefined) {
      kmInput.value = group.kmDriven;
    }
    kmInput.addEventListener("input", () => {
      group.kmDriven = kmInput.value === "" ? null : Number(kmInput.value);
      onChanged();
    });
    kmField.appendChild(kmInput);
    const kmHint = document.createElement("p");
    kmHint.className = "hint";
    kmHint.textContent = STRINGS.review.kmDrivenWhy;
    kmField.appendChild(kmHint);
    card.appendChild(kmField);

    const hoursField = document.createElement("div");
    hoursField.className = "field";
    const hoursLabel = document.createElement("label");
    hoursLabel.textContent = STRINGS.review.hoursOnline;
    hoursField.appendChild(hoursLabel);
    const hoursInput = document.createElement("input");
    hoursInput.type = "number";
    hoursInput.min = "0";
    hoursInput.step = "0.01";
    if (group.hoursOnline !== null && group.hoursOnline !== undefined) {
      hoursInput.value = group.hoursOnline;
    }
    hoursInput.addEventListener("input", () => {
      group.hoursOnline = hoursInput.value === "" ? null : Number(hoursInput.value);
      onChanged();
    });
    hoursField.appendChild(hoursInput);
    const hoursHint = document.createElement("p");
    hoursHint.className = "hint";
    hoursHint.textContent = STRINGS.review.hoursOnlineWhy;
    hoursField.appendChild(hoursHint);
    card.appendChild(hoursField);

    block.appendChild(card);
    groupsEl.appendChild(block);
  }

  document.getElementById("btn-review-continue").textContent = STRINGS.review.confirmAndContinue;
  document.getElementById("review-continue-hint").textContent = STRINGS.review.mustConfirmAll;
  updateContinueButtonState();
}

function allTripFieldsConfirmed(trip) {
  return (
    trip.date.confirmed
    && trip.basePay.confirmed
    && trip.incentive.confirmed
    && trip.tip.confirmed
    && trip.totalPayout.confirmed
    && trip.distanceKm.confirmed
    && trip.durationMin.confirmed
    && trip.deductions.confirmed
  );
}

function reviewIsComplete() {
  if (state.mode === "trip") {
    const allTrips = state.tripGroups.flatMap((g) => g.trips);
    if (allTrips.length === 0) {
      return false;
    }
    return allTrips.every(allTripFieldsConfirmed);
  }
  if (state.mode === "weekly") {
    const g = state.weekGroup;
    if (!g) return false;
    return (
      g.periodLabel.confirmed
      && g.lines.confirmed
      && g.deductions.confirmed
      && g.totalCredited.confirmed
      && g.kmDriven !== null && g.kmDriven !== undefined
      && g.hoursOnline !== null && g.hoursOnline !== undefined
    );
  }
  return false;
}

function updateContinueButtonState() {
  const btn = document.getElementById("btn-review-continue");
  const hint = document.getElementById("review-continue-hint");
  const ready = reviewIsComplete();
  btn.disabled = !ready;
  hint.hidden = ready;
}

async function handleReviewContinue() {
  try {
    if (state.mode === "trip") {
      const trips = state.tripGroups.flatMap((g) => g.trips).map((t) => ({
        trip_date: t.date.value,
        date_confirmed: t.date.confirmed,
        base_pay: t.basePay.value,
        incentive: t.incentive.value,
        tip: t.tip.value,
        deductions: t.deductions.items.map((d) => ({ label: d.label || "Deduction", amount: d.amount || 0 })),
        total_payout: t.totalPayout.value,
        distance_km: t.distanceKm.value,
        duration_min: t.durationMin.value,
      }));
      setLoading(true, STRINGS.common.loading);
      await api.putTrips(trips);
    } else if (state.mode === "weekly") {
      const g = state.weekGroup;
      const week = {
        period_label: g.periodLabel.value,
        lines: g.lines.items.map((l) => ({ label: l.label || "Earning", amount: l.amount || 0 })),
        deductions: g.deductions.items.map((d) => ({ label: d.label || "Deduction", amount: d.amount || 0 })),
        total_credited: g.totalCredited.value,
        km_driven: g.kmDriven,
        hours_online: g.hoursOnline,
      };
      setLoading(true, STRINGS.common.loading);
      await api.putWeek(week);
    }
    setLoading(false);
    renderCosts();
    showScreen("costs");
  } catch (err) {
    setLoading(false);
    showApiError(err);
  }
}

// ---------------------------------------------------------------------------
// Screen c: rejected
// ---------------------------------------------------------------------------

function renderRejected(reason) {
  state.lastRejectedReason = reason;
  document.getElementById("rejected-title").textContent = STRINGS.rejected.title;
  document.getElementById("rejected-reason").textContent = reason;
  document.getElementById("btn-try-another").textContent = STRINGS.rejected.tryAnother;
}

function setupRejectedScreen() {
  document.getElementById("btn-try-another").addEventListener("click", () => {
    resetState();
    showScreen("landing");
  });
}

// ---------------------------------------------------------------------------
// Screen d: costs
// ---------------------------------------------------------------------------

function renderCosts() {
  document.getElementById("costs-title").textContent = STRINGS.costs.title;
  document.getElementById("label-fuel").textContent = moneyLabel(STRINGS.costs.fuel);
  document.getElementById("label-maintenance").textContent = moneyLabel(STRINGS.costs.maintenance);
  document.getElementById("label-fixed-daily").textContent = moneyLabel(STRINGS.costs.fixedDaily);
  document.getElementById("hint-fixed-daily").textContent = STRINGS.costs.fixedDailyWhy;
  document.getElementById("label-hours-online").textContent = STRINGS.costs.hoursOnline;
  document.getElementById("hint-hours-online").textContent = STRINGS.costs.hoursOnlineWhy;
  document.getElementById("btn-save-costs").textContent = STRINGS.costs.save;
  document.getElementById("costs-saved-note").hidden = true;

  // Sample mode: prefill plausible defaults so there's nothing to type
  // unless the visitor wants to change them (CLAUDE.md step 2).
  document.getElementById("input-fuel").value = state.isSampleMode ? SAMPLE_DEFAULT_FUEL_PER_KM : "";
  document.getElementById("input-maintenance").value = state.isSampleMode ? SAMPLE_DEFAULT_MAINTENANCE_PER_KM : "";
  document.getElementById("input-fixed-daily").value = "";
  document.getElementById("input-hours-online").value = state.isSampleMode && state.mode === "trip" ? SAMPLE_DEFAULT_TRIP_HOURS_ONLINE : "";

  // Weekly mode already collects hours_online as part of the week record
  // (FE-5): the costs screen's "hours online" field is trip mode only.
  document.getElementById("field-hours-online").hidden = state.mode !== "trip";
}

async function handleSaveCosts() {
  const fuel = document.getElementById("input-fuel").value;
  const maintenance = document.getElementById("input-maintenance").value;
  const fixedDaily = document.getElementById("input-fixed-daily").value;
  const hoursOnline = document.getElementById("input-hours-online").value;

  if (fuel === "" || maintenance === "") {
    showToast(STRINGS.review.mustConfirmAll);
    return;
  }

  const body = {
    fuel_cost_per_km: Number(fuel),
    maintenance_cost_per_km: Number(maintenance),
    fixed_cost_per_day: fixedDaily === "" ? null : Number(fixedDaily),
  };

  if (state.mode === "trip") {
    state.loggedInHoursEntered = hoursOnline === "" ? null : Number(hoursOnline);
  }

  try {
    setLoading(true, STRINGS.common.loading);
    await api.putCosts(body);
    showToast(STRINGS.costs.saved);
    await fetchAndShowResults();
  } catch (err) {
    setLoading(false);
    showApiError(err);
  }
}

// ---------------------------------------------------------------------------
// Screen e: results
// ---------------------------------------------------------------------------

function createRateCard(labelText, valueText, noteText, delayIndex) {
  const card = document.createElement("div");
  card.className = "card rate-card tilt-card fade-slide-in";
  card.style.setProperty("--stagger-index", delayIndex);

  const value = document.createElement("p");
  value.className = "rate-card-value";
  value.textContent = valueText;
  card.appendChild(value);

  const label = document.createElement("p");
  label.className = "rate-card-label";
  label.textContent = labelText;
  card.appendChild(label);

  if (noteText) {
    const note = document.createElement("p");
    note.className = "rate-card-note";
    note.textContent = noteText;
    card.appendChild(note);
  }

  return card;
}

function appendNetEarningsFigure(container, valueText) {
  const wrap = document.createElement("div");
  wrap.className = "results-hero";
  const label = document.createElement("p");
  label.className = "net-earnings-label";
  label.textContent = STRINGS.results.netEarnings;
  const value = document.createElement("p");
  value.className = "net-earnings-value count-up";
  value.textContent = valueText;
  value.dataset.finalText = valueText;
  wrap.appendChild(label);
  wrap.appendChild(value);
  container.appendChild(wrap);
  return value;
}

function prefersReducedMotion() {
  return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Net earnings counts up over 600ms (item 7); final values appear at once
// under prefers-reduced-motion, and always land exactly on the real text
// (no floating-point drift from the animation).
function animateCountUp(el) {
  if (!el) {
    return;
  }
  const finalText = el.dataset.finalText;
  const target = parseFloat(finalText.replace(/[^\d.-]/g, ""));
  if (prefersReducedMotion() || !isFinite(target)) {
    el.textContent = finalText;
    return;
  }
  const duration = 600;
  const start = performance.now();
  function frame(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - (1 - t) * (1 - t);
    el.textContent = formatMoney(target * eased, state.currency);
    if (t < 1) {
      requestAnimationFrame(frame);
    } else {
      el.textContent = finalText;
    }
  }
  requestAnimationFrame(frame);
}

function addResultsRow(container, labelText, valueText) {
  const row = document.createElement("div");
  row.className = "results-row";
  const label = document.createElement("span");
  label.className = "label";
  label.textContent = labelText;
  const value = document.createElement("span");
  value.className = "value";
  value.textContent = valueText;
  row.appendChild(label);
  row.appendChild(value);
  container.appendChild(row);
}

async function fetchAndShowResults() {
  const loggedInHours = state.mode === "trip" ? state.loggedInHoursEntered : undefined;
  try {
    setLoading(true, STRINGS.common.loading);
    const summary = await api.getSummary(state.mode, loggedInHours);
    setLoading(false);
    renderResults(summary);
    if (!state.askAndEvidenceRendered) {
      renderAskScreen();
      renderEvidenceScreen();
      state.askAndEvidenceRendered = true;
    }
    showScreen("results");
  } catch (err) {
    setLoading(false);
    showApiError(err);
  }
}

function renderResults(summary) {
  document.getElementById("results-title").textContent = STRINGS.results.title;
  const body = document.getElementById("results-body");
  clearChildren(body);

  const currency = state.currency;
  let netEarningsEl;
  const cardsWrap = document.createElement("div");
  cardsWrap.className = "rate-cards";

  if (summary.mode === "trip") {
    netEarningsEl = appendNetEarningsFigure(body, formatMoney(summary.net_earnings, currency) ?? "—");

    cardsWrap.appendChild(createRateCard(
      STRINGS.results.perHourOnTrips,
      formatRate(summary.net_per_engaged_hour, "/ hr", currency) ?? "—",
      null,
      0,
    ));
    if (summary.net_per_logged_in_hour !== null && summary.net_per_logged_in_hour !== undefined) {
      cardsWrap.appendChild(createRateCard(
        STRINGS.results.perHourOnline,
        formatRate(summary.net_per_logged_in_hour, "/ hr", currency),
        null,
        1,
      ));
    } else {
      cardsWrap.appendChild(createRateCard(STRINGS.results.perHourOnline, "—", STRINGS.results.noLoggedInHours, 1));
    }
    body.appendChild(cardsWrap);

    const why = document.createElement("p");
    why.className = "hint why-differ";
    why.textContent = STRINGS.results.whyTheyDiffer;
    body.appendChild(why);

    addResultsRow(body, STRINGS.results.payPerKm, formatRate(summary.net_payout_per_km, "per km", currency) ?? "—");
    addResultsRow(body, STRINGS.results.deductionShare, formatPercent(summary.deduction_share) ?? "—");
  } else if (summary.mode === "weekly") {
    netEarningsEl = appendNetEarningsFigure(body, formatMoney(summary.net_earnings_weekly, currency) ?? "—");

    cardsWrap.appendChild(createRateCard(
      STRINGS.results.perHourOnTrips,
      "—",
      summary.per_hour_on_trips_unavailable,
      0,
    ));
    cardsWrap.appendChild(createRateCard(
      STRINGS.results.perHourOnline,
      formatRate(summary.net_per_online_hour, "/ hr", currency) ?? "—",
      null,
      1,
    ));
    body.appendChild(cardsWrap);

    const why = document.createElement("p");
    why.className = "hint why-differ";
    why.textContent = STRINGS.results.perHourOnTripsUnavailableNote;
    body.appendChild(why);

    addResultsRow(body, STRINGS.results.payPerKm, formatRate(summary.net_payout_per_km, "per km", currency) ?? "—");
    addResultsRow(body, STRINGS.results.deductionShare, formatPercent(summary.deduction_share) ?? "—");
  }

  if (summary.data_quality && summary.data_quality.length > 0) {
    const h3 = document.createElement("h3");
    h3.textContent = STRINGS.results.dataQualityTitle;
    body.appendChild(h3);
    const ul = document.createElement("ul");
    summary.data_quality.forEach((note) => {
      const li = document.createElement("li");
      li.textContent = note;
      ul.appendChild(li);
    });
    body.appendChild(ul);
  }

  animateCountUp(netEarningsEl);
}

// ---------------------------------------------------------------------------
// Screen f: ask
// ---------------------------------------------------------------------------

function renderAskScreen() {
  document.getElementById("ask-title").textContent = STRINGS.ask.title;
  document.getElementById("label-ask-question").textContent = STRINGS.ask.questionLabel;
  document.getElementById("btn-ask-submit").textContent = STRINGS.ask.submit;
  document.getElementById("input-ask-question").value = "";
  document.getElementById("ask-answer").hidden = true;

  const suggestionsEl = document.getElementById("ask-suggestions");
  clearChildren(suggestionsEl);
  const heading = document.createElement("p");
  heading.textContent = STRINGS.ask.suggestionsHeading;
  suggestionsEl.appendChild(heading);

  const suggestions = state.mode === "weekly" ? STRINGS.ask.suggestionsWeekly : STRINGS.ask.suggestionsTrip;
  suggestions.forEach((question) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "small suggestion-chip";
    chip.textContent = question;
    chip.addEventListener("click", () => handleAsk(question));
    suggestionsEl.appendChild(chip);
  });
}

async function handleAsk(question) {
  const text = (question || document.getElementById("input-ask-question").value || "").trim();
  if (!text) {
    return;
  }
  document.getElementById("input-ask-question").value = text;
  try {
    setLoading(true, STRINGS.common.loading);
    const result = await api.ask(text, "en");
    setLoading(false);
    const answerBlock = document.getElementById("ask-answer");
    const badge = document.getElementById("ask-verified-badge");
    const answerText = document.getElementById("ask-answer-text");
    if (result.verified) {
      badge.textContent = STRINGS.ask.verified;
      badge.hidden = false;
    } else {
      badge.hidden = true;
    }
    answerText.textContent = result.text;
    answerBlock.hidden = false;
  } catch (err) {
    setLoading(false);
    showApiError(err);
  }
}

// ---------------------------------------------------------------------------
// Screen g: evidence pack and delete
// ---------------------------------------------------------------------------

function renderEvidenceScreen() {
  document.getElementById("evidence-title").textContent = STRINGS.evidence.title;
  document.getElementById("btn-open-report").textContent = STRINGS.evidence.openReport;
  document.getElementById("evidence-privacy-note").textContent = STRINGS.evidence.privacyNote;
  document.getElementById("delete-heading").textContent = STRINGS.evidence.deleteHeading;
  document.getElementById("delete-explain").textContent = STRINGS.evidence.deleteExplain;
  document.getElementById("btn-delete-data").textContent = STRINGS.evidence.deleteButton;
  document.getElementById("delete-confirm-text").textContent = STRINGS.evidence.deleteConfirmText;
  document.getElementById("btn-delete-confirm-yes").textContent = STRINGS.evidence.deleteConfirmYes;
  document.getElementById("btn-delete-confirm-cancel").textContent = STRINGS.evidence.deleteConfirmCancel;
  document.getElementById("delete-confirm-panel").hidden = true;
  document.getElementById("btn-delete-data").hidden = false;
}

async function handleOpenReport() {
  const loggedInHours = state.mode === "trip" ? state.loggedInHoursEntered : undefined;
  // Open the tab synchronously (inside the click handler) so the browser
  // doesn't treat the later, async-filled tab as an unrequested popup.
  const reportWindow = window.open("", "_blank");
  try {
    const html = await api.getReportHtml(state.mode, loggedInHours);
    if (reportWindow) {
      reportWindow.document.open();
      reportWindow.document.write(html);
      reportWindow.document.close();
    } else {
      const blob = new Blob([html], { type: "text/html" });
      window.location.href = URL.createObjectURL(blob);
    }
  } catch (err) {
    if (reportWindow) {
      reportWindow.close();
    }
    showApiError(err);
  }
}

function showDeleteConfirm() {
  document.getElementById("delete-confirm-panel").hidden = false;
  document.getElementById("btn-delete-data").hidden = true;
}

function cancelDeleteConfirm() {
  document.getElementById("delete-confirm-panel").hidden = true;
  document.getElementById("btn-delete-data").hidden = false;
}

async function handleDeleteConfirmed() {
  try {
    setLoading(true, STRINGS.common.loading);
    await api.deleteAll();
    setLoading(false);
    resetState();
    // All stored data is gone, so Results/Ask/Evidence would have nothing to
    // show (and Results would fail with a "no trips/weeks" error if the
    // worker tapped it again) -- send them back to the start instead of
    // leaving a now-stale nav bar up.
    showScreen("landing");
    showToast(STRINGS.evidence.deleteDone);
  } catch (err) {
    setLoading(false);
    cancelDeleteConfirm();
    showApiError(err);
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

function renderStepLabels() {
  document.getElementById("step-label-1").textContent = STRINGS.steps.upload;
  document.getElementById("step-label-2").textContent = STRINGS.steps.check;
  document.getElementById("step-label-3").textContent = STRINGS.steps.costs;
  document.getElementById("step-label-4").textContent = STRINGS.steps.results;
}

export function initApp() {
  renderStepLabels();
  renderLandingStrings();
  setupLanding();
  setupRejectedScreen();
  setupLightbox();
  setupErrorLine();
  setupNav();
  document.getElementById("btn-review-continue").addEventListener("click", handleReviewContinue);
  document.getElementById("btn-save-costs").addEventListener("click", handleSaveCosts);
  document.getElementById("btn-ask-submit").addEventListener("click", () => handleAsk());
  document.getElementById("btn-open-report").addEventListener("click", handleOpenReport);
  document.getElementById("btn-delete-data").addEventListener("click", showDeleteConfirm);
  document.getElementById("btn-delete-confirm-yes").addEventListener("click", handleDeleteConfirmed);
  document.getElementById("btn-delete-confirm-cancel").addEventListener("click", cancelDeleteConfirm);
  showScreen("landing");
}
