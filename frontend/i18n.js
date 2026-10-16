// Runtime translations (stage 1, language setting). English (lang/en.json) is
// always loaded and is the fallback for any key the selected language lacks.
// The chosen language code (and nothing else) is kept in sessionStorage.
// Figures are never translated or reformatted here: digits 0-9 and the rupee
// sign come from the API and format.js in every language.
const STORAGE_KEY = "payproof_lang";
const FALLBACK = "en";

// Endonyms are the languages' own names, so they are not translation keys.
export const LANGUAGES = [
  { code: "en", name: "English", speech: "en-IN" }, // i18n-ignore
  { code: "hi", name: "हिन्दी", speech: "hi-IN" }, // i18n-ignore
  { code: "ta", name: "தமிழ்", speech: "ta-IN" }, // i18n-ignore
  { code: "te", name: "తెలుగు", speech: "te-IN" }, // i18n-ignore
  { code: "kn", name: "ಕನ್ನಡ", speech: "kn-IN" }, // i18n-ignore
  { code: "ml", name: "മലയാളം", speech: "ml-IN" }, // i18n-ignore
];

const dictionaries = {}; // code -> { key: text }, cached in memory
let currentLang = FALLBACK;
const listeners = [];

function isSupported(code) {
  return LANGUAGES.some((l) => l.code === code);
}

export function getLanguage() {
  return currentLang;
}

export function languageInfo(code = currentLang) {
  return LANGUAGES.find((l) => l.code === code) || LANGUAGES[0];
}

async function loadDictionary(code) {
  if (dictionaries[code]) {
    return dictionaries[code];
  }
  try {
    // no-cache: revalidate each time, so an updated translation is never served stale from the browser cache
    const response = await fetch(`lang/${code}.json`, { cache: "no-cache" });
    if (!response.ok) {
      throw new Error(`lang/${code}.json: ${response.status}`);
    }
    dictionaries[code] = await response.json();
  } catch (err) {
    console.error(err);
    dictionaries[code] = null; // English is used instead
  }
  return dictionaries[code];
}

function fill(text, params) {
  if (!params) {
    return text;
  }
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

// True when the selected language has its own text for this key.
export function hasOwnText(key) {
  const own = dictionaries[currentLang];
  return currentLang === FALLBACK || (!!own && typeof own[key] === "string" && own[key] !== "");
}

// t("results.title"), t("upload.processing", { current: 1, total: 2 }).
export function t(key, params) {
  const own = dictionaries[currentLang];
  const en = dictionaries[FALLBACK];
  let text = own && typeof own[key] === "string" && own[key] !== "" ? own[key] : null;
  if (text === null) {
    text = en && typeof en[key] === "string" ? en[key] : key;
  }
  return fill(text, params);
}

// Fills every element marked data-i18n="key" (text), data-i18n-aria-label,
// data-i18n-alt, data-i18n-title. An element showing English because its key
// is not translated yet is tagged lang="en" so screen readers read it right.
export function applyStaticStrings(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
    if (hasOwnText(key)) {
      el.removeAttribute("lang");
    } else {
      el.setAttribute("lang", FALLBACK);
    }
  });
  for (const attr of ["aria-label", "alt", "title"]) {
    root.querySelectorAll(`[data-i18n-${attr}]`).forEach((el) => {
      el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`)));
    });
  }
  // The "machine translation" note logic was here: see the comment in index.html to bring it back.
  document.title = t("app.name");
  fitSvgText(document.getElementById("splash-tag"), 400);
}

// SVG text cannot wrap, so shrink it until it fits the splash card.
function fitSvgText(el, maxWidth) {
  if (!el) {
    return;
  }
  try {
    el.setAttribute("font-size", "14");
    let size = 14;
    while (size > 8 && el.getComputedTextLength() > maxWidth) {
      size -= 1;
      el.setAttribute("font-size", String(size));
    }
  } catch (_) {
    // Not measurable while hidden or removed; the default size stays.
  }
}

export function onLanguageChange(callback) {
  listeners.push(callback);
}

export async function setLanguage(code) {
  const wanted = isSupported(code) ? code : FALLBACK;
  await loadDictionary(FALLBACK);
  if (wanted !== FALLBACK) {
    await loadDictionary(wanted);
  }
  currentLang = wanted;
  document.documentElement.lang = wanted;
  try {
    sessionStorage.setItem(STORAGE_KEY, wanted);
  } catch (_) {
    // Storage blocked: the choice simply lasts until the page is reloaded.
  }
  document.querySelectorAll("select[data-lang-select]").forEach((select) => {
    select.value = wanted;
  });
  applyStaticStrings();
  listeners.forEach((callback) => callback(wanted));
}

function buildLanguageSelects() {
  document.querySelectorAll("select[data-lang-select]").forEach((select) => {
    LANGUAGES.forEach((language) => {
      const option = document.createElement("option");
      option.value = language.code;
      option.lang = language.code;
      option.textContent = language.name;
      select.appendChild(option);
    });
    select.addEventListener("change", () => setLanguage(select.value));
  });
}

// Call once at start-up: builds the selectors, loads the remembered language.
export async function initI18n() {
  buildLanguageSelects();
  let saved = null;
  try {
    saved = sessionStorage.getItem(STORAGE_KEY);
  } catch (_) {
    saved = null;
  }
  await setLanguage(isSupported(saved) ? saved : FALLBACK);
}
