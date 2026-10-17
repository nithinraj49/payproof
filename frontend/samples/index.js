// Curated sample screenshots for "Try with sample screenshots" (FE-2,
// REQUIREMENTS.md section 19 rule 5). All three are from eval/generated/
// (eval/sim_config.py's fictional-platform generator, never a real app),
// copied here so Firebase Hosting can serve them -- Hosting only serves
// frontend/, not eval/. Viewed by hand before adding: no real logo, name
// or phone number appears in any of them (eval/generated/ground_truth/
// L1_001.json, L3_010.json, N1_004.json have the exact field values).
export const SAMPLE_IMAGES = [
  {
    id: "trip",
    kind: "trip",
    url: "samples/trip.jpg",
    fileName: "sample-trip.jpg",
    labelKey: "samples.trip.label",
    descriptionKey: "samples.trip.description",
  },
  {
    id: "weekly",
    kind: "weekly",
    url: "samples/weekly.jpg",
    fileName: "sample-weekly.jpg",
    labelKey: "samples.weekly.label",
    descriptionKey: "samples.weekly.description",
  },
  {
    id: "order_offer",
    kind: "order_offer",
    url: "samples/order_offer.jpg",
    fileName: "sample-order-offer.jpg",
    labelKey: "samples.orderOffer.label",
    descriptionKey: "samples.orderOffer.description",
  },
];

// Language-specific samples (stage: language sample screenshots). Images live in
// samples/<lang>/<id>.png, drawn by scripts/make_sample_images.mjs (fictional TrailDash
// app, same numbers in every language). A language lists only the images that passed the
// live extraction test; an image missing from the list shows no button for that language.
// These go through the NORMAL upload path (isSample false): no is_sample flag, no backend
// change, no sample cache, no prefilled costs.
export const LANGUAGE_SAMPLES = {
  ta: ["trip", "weekly", "order_offer"],
  hi: ["trip", "weekly", "order_offer"], // hi/weekly: first version scored 8/9 live (amounts right); restored
  te: ["trip", "weekly", "order_offer"],
  kn: ["trip", "weekly", "order_offer"],
  ml: ["trip", "weekly", "order_offer"],
};

// English keeps the existing sample mode untouched. If a language has no images listed,
// the English samples are shown rather than an empty picker.
export function samplesFor(lang) {
  const ids = LANGUAGE_SAMPLES[lang];
  if (lang === "en" || !ids || ids.length === 0) {
    return SAMPLE_IMAGES.map((sample) => ({ ...sample, isSample: true }));
  }
  return SAMPLE_IMAGES.filter((sample) => ids.includes(sample.id)).map((sample) => ({
    ...sample,
    url: `samples/${lang}/${sample.id}.png`,
    fileName: `sample-${lang}-${sample.id}.png`,
    isSample: false,
  }));
}
