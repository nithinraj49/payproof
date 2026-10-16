// Voice input for the Ask screen (stage 1). Uses the browser's own Web Speech
// API only: no audio is recorded here and nothing is sent to PayProof's
// backend. The transcript is put in the text box for the worker to check and
// edit; it is NEVER submitted automatically.
import { getLanguage, languageInfo, t } from "./i18n.js";

const MAX_LISTEN_MS = 15000;

let ui = null;
let recognition = null; // the active SpeechRecognition, from tap until it ends
let listening = false; // true once the browser has actually started listening
let timer = null;
let statusKey = null;
let statusIsError = false;

function recognitionConstructor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function setStatus(key, isError = false) {
  statusKey = key;
  statusIsError = isError;
  renderVoiceStrings();
}

// Text and state only; safe to call again on a language change.
export function renderVoiceStrings() {
  if (!ui || !recognitionConstructor()) {
    return;
  }
  const label = t(recognition ? "voice.stop" : "voice.start");
  ui.button.setAttribute("aria-label", label);
  ui.button.title = label;
  ui.button.setAttribute("aria-pressed", recognition ? "true" : "false");
  ui.button.classList.toggle("listening", listening);
  ui.privacyNote.textContent = t("voice.privacy");
  ui.checkNote.textContent = t("voice.checkWords");
  ui.status.textContent = statusKey ? t(statusKey) : "";
  ui.status.hidden = !statusKey;
  ui.status.classList.toggle("error-banner", statusIsError);
}

function errorKey(code) {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "voice.permissionDenied";
    case "no-speech":
      return "voice.noSpeech";
    case "audio-capture":
      return "voice.noMic";
    case "network":
      return "voice.network";
    default:
      return "voice.failed";
  }
}

function finish(rec, transcript, errorCode) {
  if (recognition !== rec) {
    return; // a session that was already replaced
  }
  clearTimeout(timer);
  timer = null;
  const discarded = rec.discarded === true;
  recognition = null;
  listening = false;

  const text = transcript.trim();
  if (discarded) {
    setStatus(null);
  } else if (text) {
    ui.input.value = text.slice(0, ui.input.maxLength > 0 ? ui.input.maxLength : 500);
    ui.checkNote.hidden = false;
    setStatus(null);
    ui.input.focus();
  } else if (errorCode === "aborted") {
    setStatus(null);
  } else {
    setStatus(errorKey(errorCode || "no-speech"), true);
  }
  renderVoiceStrings();
}

function start() {
  const Recognition = recognitionConstructor();
  const rec = new Recognition();
  rec.lang = languageInfo(getLanguage()).speech;
  rec.continuous = false; // the browser ends the session itself after silence
  rec.interimResults = false;
  rec.maxAlternatives = 1;

  let transcript = "";
  let errorCode = null;
  rec.onstart = () => {
    listening = true;
    setStatus("voice.listening");
    timer = setTimeout(() => {
      try {
        rec.stop();
      } catch (_) {
        // Already stopped.
      }
    }, MAX_LISTEN_MS);
  };
  rec.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      if (event.results[i].isFinal) {
        transcript += `${event.results[i][0].transcript} `;
      }
    }
  };
  rec.onerror = (event) => {
    errorCode = event.error;
  };
  rec.onend = () => finish(rec, transcript, errorCode);

  ui.checkNote.hidden = true;
  recognition = rec;
  setStatus(null);
  try {
    rec.start();
  } catch (_) {
    recognition = null;
    setStatus("voice.failed", true);
  }
}

function toggle() {
  if (recognition) {
    // Second tap: stop and keep what was heard. Before the browser has
    // started listening (waiting on the permission prompt) there is nothing
    // to keep, so cancel.
    if (listening) {
      recognition.stop();
    } else {
      recognition.discarded = true;
      recognition.abort();
    }
    return;
  }
  start();
}

// Cancels any listening and drops what was heard (leaving the Ask screen, a
// language change, the page being hidden).
export function stopVoice() {
  if (!recognition) {
    return;
  }
  recognition.discarded = true;
  try {
    recognition.abort();
  } catch (_) {
    // Already stopped.
  }
}

// If the browser has no speech recognition the button and its note stay
// hidden (as in index.html) and nothing else on the screen changes.
export function initVoice(elements) {
  ui = elements;
  if (!recognitionConstructor()) {
    return;
  }
  ui.button.hidden = false;
  ui.privacyNote.hidden = false;
  ui.button.addEventListener("click", toggle);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopVoice();
    }
  });
  renderVoiceStrings();
}
