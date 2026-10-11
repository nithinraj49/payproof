// All user-visible text lives here (CLAUDE.md "language scope" / FE-11).
// English only for now. Keep this the single source of truth for every
// label, button, error and explanation shown anywhere in frontend/.
export const STRINGS = {
  app: {
    name: "PayProof",
    signingIn: "Signing in…",
    signInFailed: "Sign-in failed. Please reload the page.",
  },

  landing: {
    tagline: "PayProof tells you what you really earn per hour, from screenshots you already have.",
    trySample: "Try with sample screenshots",
    trySampleComingSoon: "Sample screenshots are coming soon. Please upload your own screenshots for now.",
    upload: "Upload my screenshots",
    privacyNote: "Your screenshots are not stored. We only keep the numbers you confirm.",
  },

  upload: {
    chooseFiles: "Choose screenshot(s)",
    processing: (current, total) => `Processing screenshot ${current} of ${total}…`,
    noFileChosen: "Please choose at least one screenshot.",
    modeMismatch: "This screenshot doesn't match the type you're already reviewing (trip vs weekly). It was skipped.",
  },

  review: {
    title: "Check these numbers against your screenshot",
    needsReviewBanner: "This screenshot may be unreadable: check every number against your screenshot.",
    rejectedInBatch: "Some screenshots were not usable and were skipped:",
    tripCardTitle: "Trip",
    weeklyCardTitle: "Weekly payout",
    orderId: "Order ID",
    orderType: "Order type",
    date: "Date",
    confirmDate: "Confirm date",
    dateConfirmed: "Date confirmed",
    basePay: "Base pay",
    incentive: "Incentive",
    tip: "Tip",
    totalPayout: "Total payout",
    distanceKm: "Distance (km)",
    durationMin: "Duration (min)",
    deductions: "Deductions",
    deductionLabel: "What was this deduction for?",
    deductionAmount: "Amount",
    addDeduction: "+ Add deduction",
    removeDeduction: "Remove",
    confirm: "Confirm",
    confirmed: "Confirmed",
    addTrip: "+ Add another trip",
    removeTrip: "Remove this trip",
    periodLabel: "Pay period",
    creditedOn: "Credited on (from screenshot, informational only)",
    lines: "Earnings",
    lineLabel: "What is this earning line?",
    lineAmount: "Amount",
    addLine: "+ Add earning line",
    totalCredited: "Total credited (shown on your screenshot)",
    kmDriven: "Kilometres driven this week",
    hoursOnline: "Hours online this week",
    kmDrivenWhy: "Used to work out your cost per kilometre.",
    hoursOnlineWhy: "Used to work out your net pay per hour online.",
    confirmAndContinue: "Confirm and continue",
    mustConfirmAll: "Please confirm every highlighted field before continuing.",
    blankFieldHint: "Not readable from your screenshot — type the value from your screenshot.",
  },

  rejected: {
    title: "We couldn't use this screenshot",
    tryAnother: "Try another screenshot",
    genericReason: "This doesn't look like a trip or payout screenshot.",
  },

  costs: {
    title: "Your costs",
    fuel: "Fuel cost per kilometre",
    maintenance: "Maintenance cost per kilometre",
    fixedDaily: "Fixed daily cost (optional)",
    fixedDailyWhy: "Any daily cost you pay regardless of how much you drive, such as a vehicle rental.",
    hoursOnline: "Hours online",
    hoursOnlineWhy: "Time you were logged in, including waiting for an order — not just time spent driving a trip.",
    save: "Save costs",
    saved: "Costs saved. Your results screen is coming next.",
    enteredHoursNote: (hours) => `You entered ${hours} hours online.`,
  },

  common: {
    loading: "Loading…",
    retry: "Try again",
    back: "Back",
    close: "Close",
  },

  errors: {
    notSignedIn: "Still signing you in — please wait a moment and try again.",
    sessionExpired: "Your session expired. Please reload the page.",
    network: "Could not reach PayProof. Check your connection and try again.",
    timeout: "That took too long. Please try again.",
    tooLarge: "That screenshot is too large. Please upload a smaller image.",
    badType: "Please upload a PNG, JPEG or WebP image.",
    busy: "PayProof is busy right now. Please try again in a minute.",
    generic: "Something went wrong. Please try again.",
  },
};
