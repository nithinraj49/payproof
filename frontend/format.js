// Shared display-formatting helpers (money, rate, percent, date). Pure
// functions, no DOM access, so both app.js and any future screen can import
// them without duplicating the Indian-digit-grouping logic.

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function currencySymbol(code) {
  // The app only ever shows rupees in practice (no per-user currency is
  // stored anywhere yet); this still reads the extraction result's own
  // `currency` field so a non-INR screenshot isn't silently mislabelled.
  if (!code || code === "INR" || code === "Rs" || code === "Rs.") {
    return "₹";
  }
  return code;
}

// "123456" -> "1,23,456": last 3 digits form one group, every group before
// that is 2 digits (Indian digit grouping, REQUIREMENTS.md section 7.2's
// "1,23,456" example) -- not the Western 3-3-3 grouping.
function indianGroupedInteger(digits) {
  if (digits.length <= 3) {
    return digits;
  }
  const last3 = digits.slice(-3);
  let rest = digits.slice(0, -3);
  const groups = [];
  while (rest.length > 2) {
    groups.unshift(rest.slice(-2));
    rest = rest.slice(0, -2);
  }
  if (rest) {
    groups.unshift(rest);
  }
  return `${groups.join(",")},${last3}`;
}

function formatAmount(value) {
  const [intPart, decPart] = Math.abs(value).toFixed(2).split(".");
  return `${indianGroupedInteger(intPart)}.${decPart}`;
}

export function formatMoney(value, currency) {
  if (value === null || value === undefined) {
    return null;
  }
  const sign = value < 0 ? "-" : "";
  return `${sign}${currencySymbol(currency)}${formatAmount(value)}`;
}

export function formatRate(value, unit, currency) {
  const money = formatMoney(value, currency);
  return money === null ? null : `${money} ${unit}`;
}

export function formatPercent(value) {
  if (value === null || value === undefined) {
    return null;
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

// Unambiguous "8 Oct 2026" text next to every date value, so day/month can
// never be misread as the other.
export function formatDateHuman(isoDate) {
  if (!isoDate) {
    return null;
  }
  const parts = String(isoDate).split("-");
  if (parts.length !== 3) {
    return null;
  }
  const [year, month, day] = parts.map((p) => parseInt(p, 10));
  if (!year || !month || !day || month < 1 || month > 12) {
    return null;
  }
  return `${day} ${MONTH_NAMES[month - 1]} ${year}`;
}
