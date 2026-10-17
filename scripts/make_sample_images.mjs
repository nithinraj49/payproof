#!/usr/bin/env node
// Dev-only (not deployed). Draws the language-specific sample screenshots into
// frontend/samples/<lang>/{trip,weekly,order_offer}.png with headless Edge/Chrome
// (it shapes Indic scripts correctly; Pillow here has no complex-text support).
// FICTIONAL platform only ("TrailDash Partner"); amounts and counts are the same in every
// language (digits 0-9, rupee sign); only the labels are translated, in simple words
// taken from the app's own language files. The wording is unreviewed.
// Run: node scripts/make_sample_images.mjs [lang ...] [--only=trip|weekly|order_offer] [--clean=te/trip,kn/weekly]
// env: EDGE=<path to msedge.exe or chrome.exe>
import { spawnSync } from "child_process";
import { mkdirSync, writeFileSync, rmSync } from "fs";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const EDGE = process.env.EDGE || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

// The numbers (the same in every language and in the English TrailDash test images).
const TRIP = { orderId: "TR-90417", base: "₹72.50", incentive: "₹15.00", tip: "₹20.00", fee: "-₹9.40", total: "₹98.10", km: "6.8", min: "31" };
const WEEK = { orders: "₹6,420.00", incentive: "₹1,150.00", tips: "₹380.00", platform: "-₹410.00", insurance: "-₹120.00", total: "₹7,420.00" };
const OFFER = { expected: "₹64", pickup: "1.2", drop: "3.4", away: "6", shopNo: "12" };

const L = {
  ta: {
    font: "Nirmala UI",
    trip: { title: "பயண விவரங்கள்", sub: "முடிந்தது", done: "டெலிவரி முடிந்தது", orderId: "ஆர்டர் எண்", date: "08 அக் 2026, 7:42 PM", sec: "பயணம்", dist: "தூரம்", kmUnit: "கி.மீ", time: "பயண நேரம்", minUnit: "நிமிடம்", earn: "வருமானம்", base: "அடிப்படை ஊதியம்", incentive: "ஊக்கத்தொகை", tip: "வாடிக்கையாளர் டிப்ஸ்", fee: "தளக் கட்டணம்", total: "மொத்தத் தொகை" },
  },
  hi: {
    font: "Nirmala UI",
    trip: { title: "ट्रिप का विवरण", sub: "पूरी हुई", done: "डिलीवरी पूरी हुई", orderId: "ऑर्डर आईडी", date: "08 अक्टू 2026, 7:42 PM", sec: "ट्रिप", dist: "दूरी", kmUnit: "किमी", time: "ट्रिप का समय", minUnit: "मिनट", earn: "कमाई", base: "मूल भुगतान", incentive: "इंसेंटिव", tip: "ग्राहक की टिप", fee: "प्लेटफ़ॉर्म शुल्क", total: "कुल भुगतान" },
    weekly: { title: "साप्ताहिक कमाई", sub: "भुगतान इतिहास", week: "सप्ताह", dates: "05 अक्टू - 11 अक्टू 2026", credited: "जमा होने की तारीख़: 13 अक्टू 2026", earn: "कमाई", orders: "ऑर्डर की कमाई", incentive: "इंसेंटिव", tips: "टिप", ded: "कटौती", platform: "प्लेटफ़ॉर्म शुल्क", insurance: "बीमा", total: "कुल जमा रकम" },
    offer: { title: "नया ऑर्डर!", sub: "डिलीवरी अनुरोध", map: "नक्शा", expected: "अनुमानित कमाई", pickup: "पिकअप की दूरी", drop: "ड्रॉप की दूरी", kmUnit: "किमी", from: "यहाँ से उठाएँ", shop: "सनराइज़ बेकरी", addr: "दुकान", addr2: "मार्केट रोड, पुराना शहर", away: "मिनट दूर", accept: "ऑर्डर स्वीकार करें" },
  },
  te: {
    font: "Nirmala UI",
    trip: { title: "ట్రిప్ వివరాలు", sub: "పూర్తయింది", done: "డెలివరీ పూర్తయింది", orderId: "ఆర్డర్ ఐడి", date: "08 అక్టో 2026, 7:42 PM", sec: "ట్రిప్", dist: "దూరం", kmUnit: "కి.మీ", time: "ట్రిప్ సమయం", minUnit: "నిమిషాలు", earn: "ఆదాయం", base: "ప్రాథమిక చెల్లింపు", incentive: "ప్రోత్సాహకం", tip: "కస్టమర్ టిప్", fee: "ప్లాట్‌ఫామ్ రుసుము", total: "మొత్తం చెల్లింపు" },
    weekly: { title: "వారపు ఆదాయం", sub: "చెల్లింపు చరిత్ర", week: "వారం", dates: "05 అక్టో - 11 అక్టో 2026", credited: "జమ అయిన తేదీ: 13 అక్టో 2026", earn: "ఆదాయం", orders: "ఆర్డర్ ఆదాయం", incentive: "ప్రోత్సాహకం", tips: "టిప్స్", ded: "తగ్గింపులు", platform: "ప్లాట్‌ఫామ్ రుసుములు", insurance: "బీమా", total: "మొత్తం జమ" },
    offer: { title: "కొత్త ఆర్డర్!", sub: "డెలివరీ అభ్యర్థన", map: "మ్యాప్", expected: "అంచనా ఆదాయం", pickup: "పికప్ దూరం", drop: "డ్రాప్ దూరం", kmUnit: "కి.మీ", from: "ఇక్కడ నుండి తీసుకోండి", shop: "సన్‌రైజ్ బేకరీ", addr: "షాప్", addr2: "మార్కెట్ రోడ్, పాత పట్టణం", away: "నిమిషాల దూరంలో", accept: "ఆర్డర్‌ను అంగీకరించండి" },
  },
  kn: {
    font: "Nirmala UI",
    trip: { title: "ಟ್ರಿಪ್ ವಿವರಗಳು", sub: "ಮುಗಿದಿದೆ", done: "ಡೆಲಿವರಿ ಮುಗಿದಿದೆ", orderId: "ಆರ್ಡರ್ ಐಡಿ", date: "08 ಅಕ್ಟೋ 2026, 7:42 PM", sec: "ಟ್ರಿಪ್", dist: "ದೂರ", kmUnit: "ಕಿಮೀ", time: "ಟ್ರಿಪ್ ಸಮಯ", minUnit: "ನಿಮಿಷ", earn: "ಗಳಿಕೆ", base: "ಮೂಲ ಪಾವತಿ", incentive: "ಪ್ರೋತ್ಸಾಹಧನ", tip: "ಗ್ರಾಹಕರ ಟಿಪ್", fee: "ಪ್ಲಾಟ್‌ಫಾರ್ಮ್ ಶುಲ್ಕ", total: "ಒಟ್ಟು ಪಾವತಿ" },
    weekly: { title: "ವಾರದ ಗಳಿಕೆ", sub: "ಪಾವತಿ ಇತಿಹಾಸ", week: "ವಾರ", dates: "05 ಅಕ್ಟೋ - 11 ಅಕ್ಟೋ 2026", credited: "ಜಮೆ ಆದ ದಿನಾಂಕ: 13 ಅಕ್ಟೋ 2026", earn: "ಗಳಿಕೆ", orders: "ಆರ್ಡರ್ ಗಳಿಕೆ", incentive: "ಪ್ರೋತ್ಸಾಹಧನ", tips: "ಟಿಪ್ಸ್", ded: "ಕಡಿತಗಳು", platform: "ಪ್ಲಾಟ್‌ಫಾರ್ಮ್ ಶುಲ್ಕಗಳು", insurance: "ವಿಮೆ", total: "ಒಟ್ಟು ಜಮೆ" },
    offer: { title: "ಹೊಸ ಆರ್ಡರ್!", sub: "ಡೆಲಿವರಿ ವಿನಂತಿ", map: "ನಕ್ಷೆ", expected: "ನಿರೀಕ್ಷಿತ ಗಳಿಕೆ", pickup: "ಪಿಕಪ್ ದೂರ", drop: "ಡ್ರಾಪ್ ದೂರ", kmUnit: "ಕಿಮೀ", from: "ಇಲ್ಲಿಂದ ತೆಗೆದುಕೊಳ್ಳಿ", shop: "ಸನ್‌ರೈಸ್ ಬೇಕರಿ", addr: "ಅಂಗಡಿ", addr2: "ಮಾರ್ಕೆಟ್ ರಸ್ತೆ, ಹಳೆಯ ಪಟ್ಟಣ", away: "ನಿಮಿಷ ದೂರದಲ್ಲಿ", accept: "ಆರ್ಡರ್ ಸ್ವೀಕರಿಸಿ" },
  },
  ml: {
    font: "Nirmala UI",
    trip: { title: "ട്രിപ്പ് വിവരങ്ങൾ", sub: "പൂർത്തിയായി", done: "ഡെലിവറി പൂർത്തിയായി", orderId: "ഓർഡർ ഐഡി", date: "08 ഒക്ടോ 2026, 7:42 PM", sec: "ട്രിപ്പ്", dist: "ദൂരം", kmUnit: "കി.മീ", time: "ട്രിപ്പ് സമയം", minUnit: "മിനിറ്റ്", earn: "വരുമാനം", base: "അടിസ്ഥാന വേതനം", incentive: "ഇൻസെന്റീവ്", tip: "ഉപഭോക്താവിന്റെ ടിപ്പ്", fee: "പ്ലാറ്റ്ഫോം ഫീസ്", total: "ആകെ തുക" },
    weekly: { title: "ആഴ്ചത്തെ വരുമാനം", sub: "പേയ്‌മെന്റ് ചരിത്രം", week: "ആഴ്ച", dates: "05 ഒക്ടോ - 11 ഒക്ടോ 2026", credited: "വരവ് വെച്ച തീയതി: 13 ഒക്ടോ 2026", earn: "വരുമാനം", orders: "ഓർഡർ വരുമാനം", incentive: "ഇൻസെന്റീവ്", tips: "ടിപ്പുകൾ", ded: "കിഴിവുകൾ", platform: "പ്ലാറ്റ്ഫോം ചാർജുകൾ", insurance: "ഇൻഷുറൻസ്", total: "ആകെ വരവ്" },
    offer: { title: "പുതിയ ഓർഡർ!", sub: "ഡെലിവറി അഭ്യർത്ഥന", map: "ഭൂപടം", expected: "പ്രതീക്ഷിക്കുന്ന വരുമാനം", pickup: "പിക്കപ്പ് ദൂരം", drop: "ഡ്രോപ്പ് ദൂരം", kmUnit: "കി.മീ", from: "ഇവിടെ നിന്ന് എടുക്കുക", shop: "സൺറൈസ് ബേക്കറി", addr: "കട", addr2: "മാർക്കറ്റ് റോഡ്, പഴയ നഗരം", away: "മിനിറ്റ് അകലെ", accept: "ഓർഡർ സ്വീകരിക്കുക" },
  },
};

const BASE_CSS = `*{box-sizing:border-box;margin:0;padding:0}html,body{width:1080px;height:1920px;overflow:hidden}
body{font-family:"{FONT}","Nirmala UI","Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.status{height:100px;display:flex;justify-content:space-between;align-items:center;padding:0 48px;font-size:32px}
.band{height:161px;padding:30px 48px 0}.band h1{font-size:50px;font-weight:700;line-height:1.25}.band p{font-size:28px;margin-top:8px;line-height:1.3}
.row{display:flex;justify-content:space-between;align-items:center;height:84px;margin:0 48px;font-size:38px;border-bottom:2px solid var(--rule)}
.row b{font-weight:400}.sec{margin:34px 48px 4px;font-size:32px;font-weight:700}`;

// "Clean" layout (used once for an image that failed the live extraction test): ISO dates, which
// the extractor can read without guessing, a Latin-only subtitle, and larger text.
function page(kind, lang, t0, clean = false) {
  let t = t0;
  if (clean) {
    t = { ...t0 };
    if (t.date) t.date = "2026-10-08, 7:42 PM";
    if (t.dates) t.dates = "2026-10-05 - 2026-10-11";
    if (t.credited) t.credited = t.credited.replace(/\d{1,2} [^\d\s]+ 2026/, "2026-10-13");
    t.sub = "";
  }
  const css = BASE_CSS.replace("{FONT}", L[lang].font) + (clean ? ".row{font-size:42px;height:92px}.sec{font-size:36px}.band h1{font-size:54px}" : "");
  if (kind === "trip") {
    return `<html lang="${lang}"><style>${css}body{background:#fbfbf9;color:#1f1f1d;--rule:#d4d4d0}
.status{color:#1f1f1d}.band{background:#1b5f7b;color:#fff}.band p{color:#e4f0f5}
.done{margin:56px 48px 0;font-size:46px;font-weight:700;color:#1b5f7b}.meta{margin:12px 48px 0;font-size:34px;color:#555;line-height:1.45}
.sec{color:#777;margin-top:46px}.neg{color:#b3261e}.totalbar{background:#eaf4ec;margin-top:30px;height:150px;display:flex;justify-content:space-between;align-items:center;padding:0 48px}
.totalbar span{font-size:46px;font-weight:700}.totalbar b{font-size:64px;color:#136b3d}</style><body>
<div class="status"><span>9:41</span><span>5G 86%</span></div>
<div class="band"><h1>${t.title}</h1><p>TrailDash Partner${t.sub ? " &nbsp;|&nbsp; " + t.sub : ""}</p></div>
<div class="done">${t.done}</div><div class="meta">${t.orderId}: ${TRIP.orderId}<br>${t.date}</div>
<div class="sec">${t.sec}</div>
<div class="row"><span>${t.dist}</span><b>${TRIP.km} ${t.kmUnit}</b></div>
<div class="row"><span>${t.time}</span><b>${TRIP.min} ${t.minUnit}</b></div>
<div class="sec">${t.earn}</div>
<div class="row"><span>${t.base}</span><b>${TRIP.base}</b></div>
<div class="row"><span>${t.incentive}</span><b>${TRIP.incentive}</b></div>
<div class="row"><span>${t.tip}</span><b>${TRIP.tip}</b></div>
<div class="row"><span>${t.fee}</span><b class="neg">${TRIP.fee}</b></div>
<div class="totalbar"><span>${t.total}</span><b>${TRIP.total}</b></div></body></html>`;
  }
  if (kind === "weekly") {
    return `<html lang="${lang}"><style>${css}body{background:#181a22;color:#f2f2f2;--rule:#3a3d48}
.band{background:#263446}.band p{color:#c8d0dc}.wk{margin:56px 48px 0;font-size:46px;font-weight:700;color:#8fd0f5}.cr{margin:14px 48px 0;font-size:34px;color:#aab}
.sec{color:#999;margin-top:44px;font-weight:400}.neg{color:#ff7a7a}.totalbar{background:#214836;margin-top:40px;height:172px;padding:38px 48px 0;position:relative}
.totalbar span{font-size:40px}.totalbar b{position:absolute;right:48px;bottom:14px;font-size:64px;color:#8ff0b0}</style><body>
<div class="status"><span>9:41</span><span>5G 86%</span></div>
<div class="band"><h1>${t.title}</h1><p>TrailDash Partner${t.sub ? " &nbsp;|&nbsp; " + t.sub : ""}</p></div>
<div class="wk">${t.week}: ${t.dates}</div><div class="cr">${t.credited}</div>
<div class="sec">${t.earn}</div>
<div class="row"><span>${t.orders}</span><b>${WEEK.orders}</b></div>
<div class="row"><span>${t.incentive}</span><b>${WEEK.incentive}</b></div>
<div class="row"><span>${t.tips}</span><b>${WEEK.tips}</b></div>
<div class="sec">${t.ded}</div>
<div class="row"><span>${t.platform}</span><b class="neg">${WEEK.platform}</b></div>
<div class="row"><span>${t.insurance}</span><b class="neg">${WEEK.insurance}</b></div>
<div class="totalbar"><span>${t.total}</span><b>${WEEK.total}</b></div></body></html>`;
  }
  return `<html lang="${lang}"><style>${css}body{background:#f5f5fa;color:#222;--rule:#d8d8e0}
.band{background:#773b8a;color:#fff}.band p{color:#eadff0}.map{width:420px;height:420px;border-radius:50%;background:#d3e1f7;border:8px solid #6482c8;margin:70px auto 0;display:flex;align-items:center;justify-content:center;font-size:40px;font-weight:700;color:#5470b4}
.exp{margin:56px 48px 36px;font-size:46px;font-weight:700}.sec{font-size:32px;font-weight:400;color:#777;margin-top:34px}
.shop{margin:8px 48px 0;font-size:46px;font-weight:700}.addr{margin:10px 48px 0;font-size:34px;color:#555}.btn{margin:96px 48px 0;height:130px;border-radius:65px;background:#279853;color:#fff;font-size:46px;font-weight:700;display:flex;align-items:center;justify-content:center}</style><body>
<div class="status"><span>9:41</span><span>5G 86%</span></div>
<div class="band"><h1>${t.title}</h1><p>TrailDash Partner${t.sub ? " &nbsp;|&nbsp; " + t.sub : ""}</p></div>
<div class="map">${t.map}</div>
<div class="exp">${t.expected}: ${OFFER.expected}</div>
<div class="row"><span>${t.pickup}</span><b>${OFFER.pickup} ${t.kmUnit}</b></div>
<div class="row"><span>${t.drop}</span><b>${OFFER.drop} ${t.kmUnit}</b></div>
<div class="sec">${t.from}</div><div class="shop">${t.shop}</div>
<div class="addr">${t.addr} ${OFFER.shopNo}, ${t.addr2}</div><div class="addr">${OFFER.away} ${t.away}</div>
<div class="btn">${t.accept}</div></body></html>`;
}

const args = process.argv.slice(2);
const only = (args.find((a) => a.startsWith("--only=")) || "").slice(7);
const cleanList = ((args.find((a) => a.startsWith("--clean=")) || "").slice(8)).split(",").filter(Boolean); // e.g. --clean=te/trip,kn/weekly
const langs = args.filter((a) => !a.startsWith("--"));
const targets = langs.length ? langs : ["ta", "hi", "te", "kn", "ml"];
const tmp = path.join(os.tmpdir(), "payproof-sample-html");
mkdirSync(tmp, { recursive: true });
const files = { trip: "trip.png", weekly: "weekly.png", offer: "order_offer.png" };
for (const lang of targets) {
  mkdirSync(path.join(root, "frontend", "samples", lang), { recursive: true });
  for (const kind of ["trip", "weekly", "offer"]) {
    if (!L[lang][kind]) continue; // Tamil weekly and order offer are the owner's existing images, copied by hand
    if (only && only !== kind && !(only === "order_offer" && kind === "offer")) continue;
    const html = path.join(tmp, `${lang}-${kind}.html`);
    writeFileSync(html, page(kind, lang, L[lang][kind], cleanList.includes(`${lang}/${kind === "offer" ? "order_offer" : kind}`)), "utf8");
    const out = path.join(root, "frontend", "samples", lang, files[kind]);
    rmSync(out, { force: true });
    const r = spawnSync(EDGE, ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=1080,1920", `--screenshot=${out}`, "--virtual-time-budget=3000", "file:///" + html.replace(/\\/g, "/")], { stdio: "ignore", timeout: 60000 });
    console.log(`${lang}/${files[kind]}: ${r.status === 0 ? "ok" : "exit " + r.status}`);
  }
}
