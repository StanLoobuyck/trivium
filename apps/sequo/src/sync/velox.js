// De browserroute met Velox; zie packages/contract/CONTRACT.md. Zonder extensie gebeurt hier niets.
import * as store from "../db/store.js";

const CHANNEL = "velox-sequo";
export const velox = { linked: false };

const post = (message) => window.postMessage({ channel: CHANNEL, from: "sequo", ...message }, location.origin);

export const linkAddress = () => `https://www.kuleuven.be/#velox-koppel=${encodeURIComponent(location.origin + location.pathname)}`;

export function startVelox({ onLinked, onResult }) {
  let working = Promise.resolve();
  window.addEventListener("message", ({ source, origin, data }) => {
    if (source !== window || origin !== location.origin) return;
    if (data?.channel !== CHANNEL || data.from !== "velox") return;
    if (data.type === "hello" && !velox.linked) {
      velox.linked = true;
      onLinked();
    }
    if (data.type !== "events" || !Array.isArray(data.events)) return;
    // Zonder semester is er niets om aan te koppelen; de wachtrij blijft dan bij Velox.
    working = working.then(async () => {
      if (!store.state.semester) return;
      onResult(await store.ingestRecordings(data.events));
      post({ type: "ack", ids: data.events.map((e) => e.id) });
    }).catch(() => {});
  });
  post({ type: "ready" });
}
