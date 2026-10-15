// Single module for every network call to the PayProof backend. Attaches the
// signed-in worker's Firebase ID token, and is the one place that turns every
// kind of failure (401, 413, 415, 429, 5xx, network failure, timeout) into a
// friendly message instead of letting a raw error reach a screen.
import { getAuth } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";
import { STRINGS } from "./strings.js";

const DEFAULT_TIMEOUT_MS = 20000;
const EXTRACT_TIMEOUT_MS = 30000;

export class ApiError extends Error {
  constructor(message, { code = "error", status = null, retryable = false } = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

async function getIdToken() {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) {
    throw new ApiError(STRINGS.errors.notSignedIn, { code: "not_signed_in" });
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
      throw new ApiError(STRINGS.errors.timeout, { code: "timeout", retryable: true });
    }
    throw new ApiError(STRINGS.errors.network, { code: "network", retryable: true });
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
  if (status === 401) {
    throw new ApiError(STRINGS.errors.sessionExpired, { code: payload?.error_code || "unauthorized", status });
  }
  if (status === 413) {
    throw new ApiError(payload?.message || STRINGS.errors.tooLarge, { code: "file_too_large", status });
  }
  if (status === 415) {
    throw new ApiError(payload?.message || STRINGS.errors.badType, { code: "unsupported_file_type", status });
  }
  if (status === 429) {
    throw new ApiError(payload?.message || STRINGS.errors.busy, { code: "daily_limit_reached", status });
  }
  if (status >= 500) {
    throw new ApiError(STRINGS.errors.busy, { code: "server_error", status, retryable: true });
  }
  throw new ApiError(payload?.message || STRINGS.errors.generic, { code: payload?.error_code || "error", status });
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
