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
