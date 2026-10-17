// Shared by run.mjs and audit.mjs: fake SpeechRecognition + a shortened 15 s timer, installed before every page load.
export const INIT_SOURCE = `
  (() => {
    const realSetTimeout = window.setTimeout.bind(window);
    window.setTimeout = (fn, ms, ...a) => realSetTimeout(fn, ms === 15000 ? 400 : ms, ...a);
    window.__srCreated = 0;
    window.__srMode = "speak"; // speak | denied | nospeech | silence | network
    class FakeSR {
      constructor() { window.__sr = this; window.__srCreated += 1; this.log = []; }
      start() {
        this.log.push("start:" + this.lang);
        if (window.__srMode === "denied") { setTimeout(() => { this.onerror && this.onerror({ error: "not-allowed" }); this.onend && this.onend(); }, 20); return; }
        if (window.__srMode === "network") { setTimeout(() => { this.onerror && this.onerror({ error: "network" }); this.onend && this.onend(); }, 20); return; }
        setTimeout(() => this.onstart && this.onstart(), 20);
        if (window.__srMode === "nospeech") setTimeout(() => { this.onerror && this.onerror({ error: "no-speech" }); this.onend && this.onend(); }, 120);
        if (window.__srMode === "silence") setTimeout(() => { this.onend && this.onend(); }, 120);
      }
      stop() { this.log.push("stop"); setTimeout(() => { if (window.__say) this.onresult && this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: window.__say }], { isFinal: true })] }); this.onend && this.onend(); }, 10); }
      abort() { this.log.push("abort"); setTimeout(() => { this.onerror && this.onerror({ error: "aborted" }); this.onend && this.onend(); }, 10); }
    }
    window.SpeechRecognition = FakeSR;
  })();
`;
