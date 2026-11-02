// Velox background — shared by every browser build.
// Tracks the lecture download state per tab and answers messages from the
// content script and popup. Where the download itself runs differs per
// browser, so the entry file (firefox.js / chrome.js / safari.js) passes in
// `runDownload` and `cancelDownload`.

import { buildLectureTitle, sanitizeFilename } from "../shared/filename.js";
import { normalizeSequoUrl, verbatimFolder } from "../shared/sequo.js";
import { isSlideUrl, slideFilename } from "../shared/slides.js";
import { loadSettings, markSlideSaved } from "../shared/storage.js";
import { forgetDelivered, reportToSequo } from "./sequo.js";
import { ext } from "../shared/ext.js";
import { describeError } from "../shared/errors.js";
import { startSiteManagement } from "./sites.js";

export { ext };

// ─── Download state (one per tab) ─────────────────────────────────────────────

const tabStates = new Map();

// Chrome stops the MV3 service worker after ~30 s without events, taking this
// Map with it, while the content script reports the lecture only once. So each
// tab's state is also kept in storage.session (cleared when the browser
// closes) and read back when the worker starts again.
const SESSION_PREFIX = "tab:";

const restored = (async () => {
  try {
    const stored = await ext.storage.session.get(null);
    for (const [key, state] of Object.entries(stored)) {
      if (key.startsWith(SESSION_PREFIX) && !tabStates.has(state.tabId)) tabStates.set(state.tabId, state);
    }
  } catch {
    // No storage.session (older browsers): state only lives in memory.
  }
})();

function persistState(state) {
  ext.storage.session?.set({ [SESSION_PREFIX + state.tabId]: state }).catch(() => {});
}

function forgetState(tabId) {
  ext.storage.session?.remove(SESSION_PREFIX + tabId).catch(() => {});
}

function createState(tabId) {
  return {
    tabId,
    available: false,
    active: false,
    jobId: null,
    url: null,
    companionUrl: null, // second picture (webcam) of a recording with two, see shared/streams.js
    pairStep: null, // while both pictures download: "companion" (0–50 %) or "main" (50–100 %)
    title: null, // Kaltura's name for the recording
    context: {}, // { course, lecture } from the Toledo page around the player
    phase: "No lecture detected",
    downloaded: 0,
    total: 0,
    percent: 0,
    speed: 0,
    eta: null,
    type: null,
    downloadId: null,
    error: null, // English, for logs; the UI shows errorCode/errorParams translated
    errorCode: null,
    errorParams: null,
  };
}

function getState(tabId) {
  if (!tabStates.has(tabId)) tabStates.set(tabId, createState(tabId));
  return tabStates.get(tabId);
}

const FINISHED_PHASES = ["Complete", "Canceled", "Download failed"];

function publishDownloadState(state) {
  if (state.tabId && (state.active || FINISHED_PHASES.includes(state.phase))) {
    ext.tabs
      .sendMessage(state.tabId, {
        action: "lectureDownloadProgress",
        ...state,
      })
      .catch(() => {
        /* Tab may have navigated away. */
      });
  }

  ext.runtime
    .sendMessage({
      action: "lectureDownloadStateChanged",
      state: { ...state },
    })
    .catch(() => {
      /* No popup listening. */
    });
}

function setDownloadState(tabId, patch, { persist = true } = {}) {
  const state = Object.assign(getState(tabId), patch);
  if (persist) persistState(state);
  publishDownloadState(state);
  return { ...state };
}

export function reportProgress(progress) {
  if (!progress.tabId) return;
  const state = getState(progress.tabId);
  if (progress.jobId && state.jobId && progress.jobId !== state.jobId) return;

  const numberOr = (value, fallback) => (Number.isFinite(value) ? value : fallback);
  let phase = progress.phase || state.phase;
  let percent = progress.percent;
  // Two pictures, one after the other: one bar, and the first one finishing isn't the end.
  if (state.pairStep && Number.isFinite(percent))
    percent = (state.pairStep === "main" ? 50 : 0) + percent / 2;
  if (state.pairStep === "companion" && phase === "Complete") phase = "Saving";
  setDownloadState(
    progress.tabId,
    {
      phase,
      downloaded: numberOr(progress.downloaded, state.downloaded),
      total: numberOr(progress.total, state.total),
      percent: numberOr(percent, state.percent),
      speed: numberOr(progress.speed, 0),
      eta: numberOr(progress.eta, null),
      active: !["Complete", "Canceled"].includes(phase),
    },
    // Progress arrives several times a second; storing every step isn't needed.
    { persist: phase !== state.phase },
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

export async function downloadFile({ url, filename, saveAs = false }) {
  return ext.downloads.download({ url, filename, saveAs });
}

// Where a running download goes (title → folder inside Downloads). Kept here
// because in Chrome the file is saved from a separate document.
const downloadFolders = new Map();

export const COMPANION_SUFFIX = ".webcam"; // Verbatim pairs "<title>.webcam.mp4" with "<title>.mp4"

export function saveFile(url, title, extension) {
  // Shortening a long title must not cut the suffix off: it pairs the webcam with the slides.
  const companion = title.endsWith(COMPANION_SUFFIX);
  const base = sanitizeFilename(companion ? title.slice(0, -COMPANION_SUFFIX.length) : title);
  const name = `${base}${companion ? COMPANION_SUFFIX : ""}.${extension}`;
  const folder = downloadFolders.get(title);
  return downloadFile({ url, filename: folder ? `${folder}/${name}` : name, saveAs: false });
}

// Resolves with the finished download, or null when it stopped halfway.
function downloadFinished(id) {
  return new Promise((resolve) => {
    const check = async () => {
      const [item] = await ext.downloads.search({ id });
      if (item?.state === "in_progress") return;
      ext.downloads.onChanged.removeListener(onChanged);
      resolve(item?.state === "complete" ? item : null);
    };
    const onChanged = (delta) => {
      if (delta.id === id && delta.state) check();
    };
    ext.downloads.onChanged.addListener(onChanged);
    check();
  });
}

// A slide file from Toledo into the course folder. Overwrites: a newer version
// of the same deck replaces the old one instead of becoming "name (1).pdf".
async function saveSlide({ url, id, title, type, code }, sender) {
  const folder = verbatimFolder(code);
  if (!folder || !isSlideUrl(url, sender.url)) return { ok: false };
  const downloadId = await ext.downloads.download({
    url,
    filename: `${folder}/${slideFilename(title, type)}`,
    saveAs: false,
    conflictAction: "overwrite",
  });
  const item = await downloadFinished(downloadId);
  if (!item) return { ok: false };
  // Logged out: Toledo answers with its login page, which must not land in the
  // course folder as a "PDF" that Verbatim would then read.
  if (item.mime?.startsWith("text/html")) {
    await ext.downloads.removeFile(downloadId).catch(() => {});
    await ext.downloads.erase({ id: downloadId }).catch(() => {});
    return { ok: false };
  }
  await markSlideSaved(code, id);
  return { ok: true };
}

function createJobId() {
  return `velox-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorMessage(error) {
  return error && error.message ? error.message : String(error);
}

// ─── Main download orchestrator ───────────────────────────────────────────────

async function startLectureDownload({ tabId, url, title, jobId }, runDownload) {
  const state = getState(tabId);
  if (state.active) {
    return { ...state };
  }

  const resolvedUrl = url || state.url;
  if (!resolvedUrl) {
    return setDownloadState(tabId, {
      available: false,
      phase: "No lecture detected",
      error: "No lecture stream has been detected yet.",
      errorCode: "errNoStream",
      errorParams: {},
    });
  }

  const resolvedTitle = sanitizeFilename(
    buildLectureTitle({ ...state.context, recording: title || state.title }),
  );
  const resolvedJobId = jobId || createJobId();
  // Only with the stream this tab detected: a URL from elsewhere has no known second picture.
  const knownCompanion = resolvedUrl === state.url ? state.companionUrl : null;

  setDownloadState(tabId, {
    ...createState(tabId),
    context: state.context,
    pageUrl: state.pageUrl,
    companionUrl: state.companionUrl,
    available: true,
    active: true,
    jobId: resolvedJobId,
    url: resolvedUrl,
    title: resolvedTitle,
    phase: "Preparing",
  });

  const { downloadsToVerbatim } = await loadSettings();
  const folder = downloadsToVerbatim ? verbatimFolder(state.context?.code) : null;
  // Two pictures: Verbatim puts them side by side, so only then the webcam too. It goes first: Verbatim waits
  // for "<title>.webcam.mp4" once "<title>.mp4" is there. Without Verbatim only the main picture (the slides).
  const companionUrl = folder ? knownCompanion : null;
  const companionTitle = `${resolvedTitle}${COMPANION_SUFFIX}`;
  if (folder) downloadFolders.set(resolvedTitle, folder);
  if (companionUrl) downloadFolders.set(companionTitle, folder);

  const run = async (downloadUrl, downloadTitle) => {
    try {
      return await runDownload({ url: downloadUrl, title: downloadTitle, tabId, jobId: resolvedJobId });
    } catch (error) {
      return { ok: false, ...describeError(error) };
    }
  };

  let response;
  if (companionUrl) {
    setDownloadState(tabId, { pairStep: "companion" });
    response = await run(companionUrl, companionTitle);
    // A webcam that fails is no reason to skip the slides; a cancel stops both.
    if (response && response.ok === false && !response.canceled)
      console.warn("Velox: webcam download failed, saving the slides only:", response.error);
    if (!response?.canceled) {
      setDownloadState(tabId, { pairStep: "main" });
      response = await run(resolvedUrl, resolvedTitle);
    }
  } else {
    response = await run(resolvedUrl, resolvedTitle);
  }
  setDownloadState(tabId, { pairStep: null });

  downloadFolders.delete(resolvedTitle);
  downloadFolders.delete(companionTitle);

  if (response && response.canceled) {
    return setDownloadState(tabId, {
      active: false,
      phase: "Canceled",
      percent: 0,
      error: null,
      errorCode: null,
    });
  }

  if (!response || response.ok === false) {
    const error = (response && response.error) || "Download failed.";
    console.error("Velox download failed:", error);
    return setDownloadState(tabId, {
      active: false,
      phase: "Download failed",
      error,
      errorCode: (response && response.errorCode) || (response && response.error ? null : "errUnknown"),
      errorParams: (response && response.errorParams) || {},
    });
  }

  reportToSequo(
    "recording.downloaded",
    { fileName: `${resolvedTitle}.${response.type || "mp4"}` },
    { context: state.context, title: title || state.title, url: state.pageUrl },
  ).catch(() => {});

  return setDownloadState(tabId, {
    active: false,
    phase: "Complete",
    percent: 100,
    type: response.type,
    downloadId: response.downloadId ?? null,
    error: null,
    errorCode: null,
  });
}

// ─── Message handler ──────────────────────────────────────────────────────────

// extraHandlers: { [action]: (msg, sender) => response | Promise<response> }
export function startBackground({ runDownload, cancelDownload, extraHandlers = {} }) {
  // The popup (and the offscreen document) pass `tabId`; content scripts
  // don't, and are identified by the tab they run in.
  const tabOf = (msg, sender) => msg.tabId ?? (sender.tab && sender.tab.id);

  const handlers = {
    saveSlide,
    registerLectureDownloadUrl(msg, sender) {
      const tabId = tabOf(msg, sender);
      const state = getState(tabId);
      return {
        ok: true,
        state: setDownloadState(tabId, {
          available: true,
          url: msg.url,
          companionUrl: msg.companionUrl ?? null,
          title: msg.title || null,
          phase: state.active ? state.phase : "Ready",
          error: state.active ? state.error : null,
        }),
      };
    },

    // From the top-level Toledo page: which course/lecture this tab shows.
    registerLectureContext(msg, sender) {
      const tabId = tabOf(msg, sender);
      const state = getState(tabId);
      state.context = { course: msg.course || null, code: msg.code || null, lecture: msg.lecture || null };
      state.pageUrl = sender.tab?.url || null;
      persistState(state);
      return { ok: true };
    },

    // From the frame with the video: how far this lecture got.
    async sequoReport(msg, sender) {
      const { context, pageUrl } = getState(tabOf(msg, sender));
      await reportToSequo(msg.type, msg.payload, { context, title: msg.title, url: pageUrl });
      return { ok: true };
    },

    async openSettings() {
      await ext.runtime.openOptionsPage();
      return { ok: true };
    },

    async sequoDelivered(msg) {
      await forgetDelivered(msg.ids);
      return { ok: true };
    },

    // Sequo's "link with Velox" arrives through a kuleuven.be page.
    async sequoOpenLink(msg) {
      const address = normalizeSequoUrl(msg.address);
      if (!address) return { ok: false };
      await ext.tabs.create({
        url: ext.runtime.getURL(`options.html#link=${encodeURIComponent(address)}`),
      });
      return { ok: true };
    },

    // "Show in folder" for the tab's finished download.
    async showDownload(msg, sender) {
      const { downloadId } = getState(tabOf(msg, sender));
      if (downloadId == null) return { ok: false };
      await ext.downloads.show(downloadId);
      return { ok: true };
    },

    getLectureDownloadState(msg, sender) {
      return { ok: true, state: { ...getState(tabOf(msg, sender)) } };
    },

    relayLectureDownloadProgress(msg) {
      reportProgress(msg);
    },

    async cancelLectureDownload(msg, sender) {
      const tabId = tabOf(msg, sender);
      const response = await cancelDownload(msg.jobId || getState(tabId).jobId);
      setDownloadState(tabId, { active: false, phase: "Canceled", percent: 0, error: null });
      return response || { ok: true };
    },

    async startLectureDownload(msg, sender) {
      const state = await startLectureDownload(
        { tabId: tabOf(msg, sender), url: msg.url, title: msg.title, jobId: msg.jobId },
        runDownload,
      );
      return { ok: !state.error, state };
    },

    ...extraHandlers,
  };

  // sendResponse + `return true` is the one async-reply style that works in
  // Chrome, Firefox and Safari alike. Every handler waits for the stored tab
  // states, so a worker that just woke up doesn't answer from an empty Map.
  ext.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    const handler = msg && msg.action && handlers[msg.action];
    if (!handler) return false;

    restored
      .then(() => handler(msg, sender))
      .then(sendResponse, (error) => sendResponse({ ok: false, error: errorMessage(error) }));
    return true;
  });

  ext.tabs.onRemoved.addListener(async (tabId) => {
    await restored;
    const state = tabStates.get(tabId);
    if (state && state.active && state.jobId) {
      Promise.resolve(cancelDownload(state.jobId)).catch(() => {});
    }
    tabStates.delete(tabId);
    forgetState(tabId);
  });

  startSiteManagement();
  if (__DEV_RELOAD__) devReloadTestPages();

  // First install: a short welcome (not for dev builds, which "install" on
  // every npm run dev:*).
  ext.runtime.onInstalled.addListener(({ reason }) => {
    if (reason === "install" && !__DEV__) ext.tabs.create({ url: ext.runtime.getURL("welcome.html") });
  });
}

// Dev builds (npm run dev:*): after a rebuild, reload open test pages so they
// get the new content script (the old one is cut off when the extension
// reloads). Once per extension load: storage.session is cleared on every
// (re)load but survives Chrome's service worker going idle and waking up.
// A test page opened before Velox was ready refreshes itself (see
// test/fixtures/index.html), so this doesn't have to catch that case.
async function devReloadTestPages() {
  try {
    const { devTestPageShown } = await ext.storage.session.get("devTestPageShown");
    if (devTestPageShown) return;
    await ext.storage.session.set({ devTestPageShown: true });
  } catch {
    // No storage.session: fine for Firefox's MV2 background page, which only
    // starts once per extension load anyway.
  }

  const tabs = await ext.tabs.query({ url: ["http://localhost/*", "http://127.0.0.1/*"] });
  for (const tab of tabs) ext.tabs.reload(tab.id);
}
