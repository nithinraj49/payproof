// Screen controller for PayProof's floor: landing -> review -> costs.
// Plain DOM manipulation, no framework, no build step (CLAUDE.md / REQUIREMENTS.md section 9).
import { api, ApiError } from "./api.js";
import { STRINGS } from "./strings.js";

let uidCounter = 0;
function uid(prefix) {
  uidCounter += 1;
  return `${prefix}-${uidCounter}`;
}

function currencySymbol(code) {
  // The app only ever shows rupees (REQUIREMENTS.md / PROGRESS.md: INR
  // throughout, no per-user currency stored yet); this still reads the
  // extraction result's own `currency` field so a non-INR screenshot isn't
  // silently mislabelled.
  if (!code || code === "INR" || code === "Rs" || code === "Rs.") {
    return "₹";
  }
  return code;
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
};

function resetState() {
  state.mode = null;
  state.currency = "INR";
  state.tripGroups = [];
  state.weekGroup = null;
  state.rejectedInBatch = [];
  state.lastRejectedReason = null;
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
};

function showScreen(name) {
  for (const key of Object.keys(screens)) {
    screens[key].hidden = key !== name;
  }
  window.scrollTo(0, 0);
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

function clearChildren(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

// ---------------------------------------------------------------------------
// Screen a: landing
// ---------------------------------------------------------------------------

function renderLandingStrings() {
  document.getElementById("landing-tagline").textContent = STRINGS.landing.tagline;
  document.getElementById("btn-try-sample").textContent = STRINGS.landing.trySample;
  document.getElementById("sample-note").textContent = STRINGS.landing.trySampleComingSoon;
  document.getElementById("upload-heading").textContent = STRINGS.landing.upload;
  document.getElementById("landing-privacy").textContent = STRINGS.landing.privacyNote;
}

function setupLanding() {
  const sampleBtn = document.getElementById("btn-try-sample");
  const sampleNote = document.getElementById("sample-note");
  sampleBtn.addEventListener("click", () => {
    sampleNote.hidden = false;
  });

  const fileInput = document.getElementById("file-input");
  fileInput.addEventListener("change", async () => {
    const files = Array.from(fileInput.files || []);
    if (files.length === 0) {
      showToast(STRINGS.upload.noFileChosen);
      return;
    }
    await handleUpload(files);
    fileInput.value = "";
  });
}

// ---------------------------------------------------------------------------
// Upload + extraction
// ---------------------------------------------------------------------------

async function handleUpload(files) {
  resetState();

  for (let i = 0; i < files.length; i += 1) {
    const file = files[i];
    setLoading(true, STRINGS.upload.processing(i + 1, files.length));

    let result;
    try {
      result = await api.extract(file, false);
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
    kmDriven: null,
    hoursOnline: null,
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

  function refresh() {
    wrap.classList.toggle("unconfirmed", !fieldState.confirmed);
    confirmBtn.textContent = fieldState.confirmed ? STRINGS.review.dateConfirmed : STRINGS.review.confirmDate;
    confirmBtn.classList.toggle("is-confirmed", fieldState.confirmed);
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
        const img = document.createElement("img");
        img.className = "preview";
        img.src = group.previewUrl;
        img.alt = "Your uploaded screenshot";
        block.appendChild(img);
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
      const img = document.createElement("img");
      img.className = "preview";
      img.src = group.previewUrl;
      img.alt = "Your uploaded screenshot";
      card.appendChild(img);
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
      p.textContent = `${STRINGS.review.creditedOn}: ${group.creditedOn}`;
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
    showToast(describeError(err));
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

  document.getElementById("input-fuel").value = "";
  document.getElementById("input-maintenance").value = "";
  document.getElementById("input-fixed-daily").value = "";
  document.getElementById("input-hours-online").value = "";

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
    setLoading(false);
    const note = document.getElementById("costs-saved-note");
    note.textContent = state.loggedInHoursEntered
      ? `${STRINGS.costs.saved} ${STRINGS.costs.enteredHoursNote(state.loggedInHoursEntered)}`
      : STRINGS.costs.saved;
    note.hidden = false;
  } catch (err) {
    setLoading(false);
    showToast(describeError(err));
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export function initApp() {
  renderLandingStrings();
  setupLanding();
  setupRejectedScreen();
  document.getElementById("btn-review-continue").addEventListener("click", handleReviewContinue);
  document.getElementById("btn-save-costs").addEventListener("click", handleSaveCosts);
  showScreen("landing");
}
