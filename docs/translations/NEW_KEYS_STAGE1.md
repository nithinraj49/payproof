# New keys added in stage 1 (language setting and voice input)

These keys exist only in `frontend/lang/en.json`. They are **not** in `docs/translations/en.json` yet, so `node scripts/check_translations.js` still passes for the five language files. Until a key is translated, the app shows the English text for it (and marks that element `lang="en"`). Keep `{placeholders}` and the rupee sign unchanged; digits stay 0 to 9.

Notes: `results.unitPerHour` and `results.unitPerKm` are the unit words shown after a rupee figure (for example `₹195.58 / hr`). `voice.*` texts appear under the microphone button on the Ask screen. `lang.machineNote` appears on every screen in the five non-English languages and should be removed per language once a person has reviewed that language.

| Key | English text |
|---|---|
| `lang.label` | Language |
| `lang.machineNote` | Machine translation, not yet reviewed |
| `samples.trip.label` | Trip screenshot |
| `samples.trip.description` | A completed delivery trip receipt. |
| `samples.weekly.label` | Weekly payout screenshot |
| `samples.weekly.description` | A week's total payout summary. |
| `samples.orderOffer.label` | Order offer (should be rejected) |
| `samples.orderOffer.description` | An incoming order offer, not a completed trip -- shows how PayProof rejects it. |
| `review.previewAlt` | Your uploaded screenshot |
| `common.lightboxAlt` | Your uploaded screenshot, enlarged |
| `results.unitPerHour` | / hr |
| `results.unitPerKm` | per km |
| `voice.start` | Speak your question |
| `voice.stop` | Stop listening |
| `voice.listening` | Listening… speak your question |
| `voice.checkWords` | Check the words before asking |
| `voice.privacy` | Voice input uses your browser's speech service (in Chrome, Google's). PayProof does not store your voice. |
| `voice.permissionDenied` | The microphone is blocked, so voice input cannot start. You can type your question instead, or allow the microphone for this site in your browser settings. |
| `voice.noSpeech` | We didn't hear anything. Tap the microphone and try again, or type your question. |
| `voice.noMic` | No microphone was found. You can type your question instead. |
| `voice.network` | Your browser's speech service could not be reached. You can type your question instead. |
| `voice.failed` | Voice input did not work. You can type your question instead. |

Same list as JSON (copy into the language file once translated):

```json
{
  "lang.label": "Language",
  "lang.machineNote": "Machine translation, not yet reviewed",
  "samples.trip.label": "Trip screenshot",
  "samples.trip.description": "A completed delivery trip receipt.",
  "samples.weekly.label": "Weekly payout screenshot",
  "samples.weekly.description": "A week's total payout summary.",
  "samples.orderOffer.label": "Order offer (should be rejected)",
  "samples.orderOffer.description": "An incoming order offer, not a completed trip -- shows how PayProof rejects it.",
  "review.previewAlt": "Your uploaded screenshot",
  "common.lightboxAlt": "Your uploaded screenshot, enlarged",
  "results.unitPerHour": "/ hr",
  "results.unitPerKm": "per km",
  "voice.start": "Speak your question",
  "voice.stop": "Stop listening",
  "voice.listening": "Listening… speak your question",
  "voice.checkWords": "Check the words before asking",
  "voice.privacy": "Voice input uses your browser's speech service (in Chrome, Google's). PayProof does not store your voice.",
  "voice.permissionDenied": "The microphone is blocked, so voice input cannot start. You can type your question instead, or allow the microphone for this site in your browser settings.",
  "voice.noSpeech": "We didn't hear anything. Tap the microphone and try again, or type your question.",
  "voice.noMic": "No microphone was found. You can type your question instead.",
  "voice.network": "Your browser's speech service could not be reached. You can type your question instead.",
  "voice.failed": "Voice input did not work. You can type your question instead."
}
```
