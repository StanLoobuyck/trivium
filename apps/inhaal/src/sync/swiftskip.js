// De browserroute met SwiftSkip; zie packages/contract/CONTRACT.md. Zonder extensie gebeurt hier niets.
import * as store from "../db/store.js";

const CHANNEL = "swiftskip-inhaal";
export const swiftskip = { linked: false };

const post = (message) => window.postMessage({ channel: CHANNEL, from: "inhaal", ...message }, location.origin);

export const linkAddress = () => `https://www.kuleuven.be/#swiftskip-koppel=${encodeURIComponent(location.origin + location.pathname)}`;

export function startSwiftSkip({ onLinked, onResult }) {
  let working = Promise.resolve();
  window.addEventListener("message", ({ source, origin, data }) => {
    if (source !== window || origin !== location.origin) return;
    if (data?.channel !== CHANNEL || data.from !== "swiftskip") return;
    if (data.type === "hello" && !swiftskip.linked) {
      swiftskip.linked = true;
      onLinked();
    }
    if (data.type !== "events" || !Array.isArray(data.events)) return;
    // Zonder semester is er niets om aan te koppelen; de wachtrij blijft dan bij SwiftSkip.
    working = working.then(async () => {
      if (!store.state.semester) return;
      onResult(await store.ingestRecordings(data.events));
      post({ type: "ack", ids: data.events.map((e) => e.id) });
    }).catch(() => {});
  });
  post({ type: "ready" });
}
