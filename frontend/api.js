// Single module for every network call to the PayProof backend. Attaches the
// signed-in worker's Firebase ID token, and is the one place that turns every
// kind of failure (401, 413, 415, 429, 5xx, network failure, timeout) into a
// friendly message instead of letting a raw error reach a screen.
import { getAuth } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";
import { getLanguage, t } from "./i18n.js";

const DEFAULT_TIMEOUT_MS = 20000;
const EXTRACT_TIMEOUT_MS = 30000;

// An error never stores a finished translated sentence: it keeps the translation KEY (and the
// backend's own English text) and works out the wording in display(), at the moment it is shown,
// so a language change re-words an error that is still on screen.
export class ApiError extends Error {
  constructor({ code = "error", status = null, retryable = false, key = null, backendMessage = null } = {}) {
    super(backendMessage || key || code); // for logs only: the screen uses display()
    this.code = code;
    this.status = status;
    this.retryable = retryable;
    this.key = key;
    this.backendMessage = backendMessage;
  }

  // English keeps the backend's own message (as in v1.0); every other language uses the
  // translated key. An error with no backend message always uses the key.
  display() {
    if (this.key && (getLanguage() !== "en" || !this.backendMessage)) {
      return t(this.key);
    }
    return this.backendMessage || t("errors.generic");
  }
}

// error_code values the backend can send (grep of backend/: auth.py, main.py, store.py,
// usage_limits.py, errors.py) -> translation key. invalid_data carries technical English text
// ("deductions[0] must not be negative"), so other languages show the generic sentence for it.
const CODE_KEYS = {
  missing_token: "errors.sessionExpired",
  invalid_token: "errors.sessionExpired",
  unsupported_file_type: "errors.badType",
  file_too_large: "errors.tooLarge",
  unreadable_image: "errors.unreadableImage",
  service_busy: "errors.busy",
  daily_limit_reached: "errors.dailyLimit",
  no_trips: "errors.noTrips",
  no_weeks: "errors.noWeeks",
  costs_not_set: "errors.costsNotSet",
  invalid_data: "errors.generic",
  unsupported_language: "errors.generic",
  http_error: "errors.generic",
};
const STATUS_KEYS = { 401: "errors.sessionExpired", 413: "errors.tooLarge", 415: "errors.badType", 429: "errors.dailyLimit" };

async function getIdToken() {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) {
    throw new ApiError({ code: "not_signed_in", key: "errors.notSignedIn" }); // i18n-ignore: error code and key, not text
  }
  return user.getIdToken();
}

async function request(path, { method = "GET", jsonBody, formBody, timeoutMs = DEFAULT_TIMEOUT_MS, parse = "json" } = {}) {
  const token = await getIdToken();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers = { Authorization: `Bearer ${token}` };
  let body;
  if (formBody !== undefined) {
    body = formBody; // browser sets the multipart Content-Type with boundary
  } else if (jsonBody !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(jsonBody);
  }

  let response;
  try {
    response = await fetch(path, { method, headers, body, signal: controller.signal });
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      throw new ApiError({ code: "timeout", retryable: true, key: "errors.timeout" }); // i18n-ignore: error code and key, not text
    }
    throw new ApiError({ code: "network", retryable: true, key: "errors.network" }); // i18n-ignore: error code and key, not text
  }
  clearTimeout(timer);

  if (response.ok) {
    if (parse === "text") {
      return response.text();
    }
    return response.json();
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    // Error body wasn't JSON (e.g. a proxy-level failure) -- fall back below.
  }

  const status = response.status;
  const code = payload?.error_code;
  if (status === 401) {
    throw new ApiError({ code: code || "unauthorized", status, key: "errors.sessionExpired" }); // i18n-ignore: error code and key, not text
  }
  if (status >= 500) {
    throw new ApiError({ code: "server_error", status, retryable: true, key: "errors.busy" }); // i18n-ignore: error code and key, not text
  }
  const key = CODE_KEYS[code] || STATUS_KEYS[status] || "errors.generic";
  const backendMessage = payload?.message || null;
  const knownCode = status === 413 ? "file_too_large" : status === 415 ? "unsupported_file_type" : status === 429 ? "daily_limit_reached" : code || "error";
  throw new ApiError({ code: knownCode, status, key, backendMessage }); // i18n-ignore: error code and key, not text
}

export const api = {
  whoami() {
    return request("/api/whoami");
  },

  extract(file, isSample = false) {
    const form = new FormData();
    form.append("file", file);
    form.append("is_sample", isSample ? "true" : "false");
    return request("/api/extract", { method: "POST", formBody: form, timeoutMs: EXTRACT_TIMEOUT_MS });
  },

  putTrips(trips) {
    return request("/api/trips", { method: "PUT", jsonBody: { trips } });
  },

  putWeek(week) {
    return request("/api/weeks", { method: "PUT", jsonBody: week });
  },

  // Stateless pre-save check (step 2, 14 Oct 2026): the review screen calls
  // this before PUT /api/weeks, so a worker can catch a missing earning
  // line while the data is still editable. No Firestore write.
  getWeeklyReconciliation(week) {
    return request("/api/weekly-reconciliation", { method: "POST", jsonBody: week });
  },

  // Stateless trip-mode check (engine figures only, no Firestore write, no
  // Gemini call): which trips do not add up to their screenshot's total.
  getTripReconciliation(trips) {
    return request("/api/trip-reconciliation", { method: "POST", jsonBody: { trips } });
  },

  putCosts(costs) {
    return request("/api/costs", { method: "PUT", jsonBody: costs });
  },

  // logged_in_hours is passed whenever the worker has entered it (CLAUDE.md
  // step A item 1); omitted entirely otherwise so the backend uses its own
  // default (no value) rather than receiving an empty string.
  getSummary(mode, loggedInHours) {
    const params = new URLSearchParams({ mode });
    if (loggedInHours !== undefined && loggedInHours !== null && loggedInHours !== "") {
      params.set("logged_in_hours", String(loggedInHours));
    }
    return request(`/api/summary?${params.toString()}`);
  },

  ask(question, language = "en") {
    return request("/api/ask", { method: "POST", jsonBody: { question, language } });
  },

  // Returns the evidence pack's raw HTML text (the caller opens it, e.g. via
  // a Blob URL) since the endpoint needs the Authorization header and so
  // can't be a plain <a href="/api/report">.
  getReportHtml(mode, loggedInHours) {
    const params = new URLSearchParams({ mode });
    if (loggedInHours !== undefined && loggedInHours !== null && loggedInHours !== "") {
      params.set("logged_in_hours", String(loggedInHours));
    }
    return request(`/api/report?${params.toString()}`, { parse: "text" });
  },

  deleteAll() {
    return request("/api/data", { method: "DELETE" });
  },
};
