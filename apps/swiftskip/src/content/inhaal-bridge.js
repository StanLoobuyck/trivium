// Runs only on the Inhaal address the user linked. Hands over the queue and
// nothing else. See packages/contract/CONTRACT.md.

import { CHANNEL } from "../shared/inhaal.js";

if (!window.swiftskipBridge) {
  window.swiftskipBridge = true;
  const QUEUE_KEY = "inhaalQueue";
  const post = (message) =>
    window.postMessage({ channel: CHANNEL, from: "swiftskip", ...message }, window.location.origin);

  const deliver = async () => {
    post({ type: "hello", version: chrome.runtime.getManifest().version });
    const queue = (await chrome.storage.local.get(QUEUE_KEY))[QUEUE_KEY] || [];
    if (queue.length) post({ type: "events", events: queue });
  };

  window.addEventListener("message", ({ source, origin, data }) => {
    if (source !== window || origin !== window.location.origin) return;
    if (data?.channel !== CHANNEL || data.from !== "inhaal") return;
    if (data.type === "ready") deliver();
    if (data.type === "ack" && Array.isArray(data.ids)) {
      chrome.runtime.sendMessage({ action: "inhaalDelivered", ids: data.ids }, () => {
        void chrome.runtime.lastError;
      });
    }
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes[QUEUE_KEY]?.newValue?.length) deliver();
  });
  deliver();
}
