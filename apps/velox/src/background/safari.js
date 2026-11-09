// Safari: no downloads API, so the download runs in the player frame
// (content/safari-download.js), which may fetch the stream like the player does.
//
// Safari doesn't deliver background → frame messages reliably (tabs.sendMessage
// with a frame id answered `undefined`), so every message goes frame →
// background: the player starts a download, then *asks* for each file of it
// (webcam, then slides), runs it, and reports the result. A cancel reaches the
// frame as the reply to its next progress message.

import { reportProgress, startBackground } from "./core.js";

const WAIT_MS = 15000;
const queued = new Map(); // jobId → { job, resolve }: waiting for the player to ask
const running = new Map(); // jobId → resolve: the player is downloading it
const askers = new Map(); // jobId → reply of a player that asked before the file was ready
const canceled = new Set();

function cancelLater(jobId) {
  canceled.add(jobId);
  setTimeout(() => canceled.delete(jobId), 60000);
}

startBackground({
  runDownload({ url, title, tabId, jobId }) {
    const job = { url, title, tabId, jobId };
    return new Promise((resolve) => {
      const asker = askers.get(jobId);
      if (asker) {
        askers.delete(jobId);
        running.set(jobId, resolve);
        asker({ job });
        return;
      }
      const entry = { job, resolve };
      queued.set(jobId, entry);
      // Started from the popup: no player asks for it.
      setTimeout(() => {
        if (queued.get(jobId) !== entry) return;
        queued.delete(jobId);
        resolve({
          ok: false,
          error: "No player took the download.",
          errorCode: "errUsePlayer",
          errorParams: {},
        });
      }, WAIT_MS);
    });
  },

  cancelDownload(jobId) {
    cancelLater(jobId);
    const result = { ok: false, canceled: true };
    queued.get(jobId)?.resolve(result);
    queued.delete(jobId);
    running.get(jobId)?.(result);
    running.delete(jobId);
    askers.get(jobId)?.({ job: null });
    askers.delete(jobId);
    return { ok: true, canceled: true };
  },

  extraHandlers: {
    // The player asks for the next file of its download (or { job: null }: done).
    safariNextDownload({ jobId }) {
      if (canceled.has(jobId)) return { job: null };
      const entry = queued.get(jobId);
      if (entry) {
        queued.delete(jobId);
        running.set(jobId, entry.resolve);
        return { job: entry.job };
      }
      return new Promise((reply) => {
        askers.set(jobId, reply);
        setTimeout(() => {
          if (askers.get(jobId) !== reply) return;
          askers.delete(jobId);
          reply({ job: null });
        }, WAIT_MS);
      });
    },

    safariDownloadDone({ jobId, result }) {
      running.get(jobId)?.(result);
      running.delete(jobId);
      return { ok: true };
    },

    // The reply carries the new state: Safari doesn't deliver the "lectureDownloadProgress"
    // messages core.js sends to the tab, so this is how the player's control stays current.
    safariDownloadProgress(msg) {
      return { cancel: canceled.has(msg.jobId), state: reportProgress(msg) };
    },
  },
});
