// The optional link with Inhaal — pure functions (unit-tested in test/).
// The message shapes are defined in packages/contract/CONTRACT.md.

// Inhaal opens https://www.kuleuven.be/#swiftskip-koppel=<its address>: a web
// page can't open an extension page itself, but SwiftSkip already runs here.
export const LINK_HOST = "www.kuleuven.be";
export const LINK_HASH = "#swiftskip-koppel=";
export const CHANNEL = "swiftskip-inhaal";
export const WATCHED_FRACTION = 0.9;
export const PROGRESS_INTERVAL_MS = 60000;
export const MIN_PROGRESS_SEC = 30;
const QUEUE_MAX = 200;

export function normalizeInhaalUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  const local = url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname);
  if (url.protocol !== "https:" && !local) return null;
  if (url.username || url.password) return null;
  const path = url.pathname.endsWith("/") ? url.pathname : `${url.pathname}/`;
  return `${url.protocol}//${url.host}${path}`;
}

export function parseLinkHash(hash) {
  if (!String(hash || "").startsWith(LINK_HASH)) return null;
  try {
    return normalizeInhaalUrl(decodeURIComponent(hash.slice(LINK_HASH.length)));
  } catch {
    return null;
  }
}

// Match patterns can't hold a port in Firefox, so both leave it out.
export function inhaalPermission(address) {
  const { protocol, hostname } = new URL(address);
  return `${protocol}//${hostname}/*`;
}

export function inhaalMatch(address) {
  const { protocol, hostname, pathname } = new URL(address);
  return `${protocol}//${hostname}${pathname}*`;
}

export function buildRecording({ code, lecture, url }) {
  if (!code || !lecture) return null;
  const recording = { courseCode: code, title: lecture };
  const date = /\b(\d{4}-\d{2}-\d{2})\b/.exec(lecture)?.[1];
  const number = /\b(?:les|lecture|college|hc)\s*(\d+)\b/i.exec(lecture)?.[1];
  if (date) recording.recordedOn = date;
  if (number && Number(number) > 0) recording.lectureNumber = Number(number);
  if (url) recording.url = url;
  return recording;
}

export function createEvent(type, recording, payload, { id, occurredAt }) {
  return { id, type, source: "swiftskip", occurredAt, payload: { recording, ...payload } };
}

const sameRecording = (a, b) =>
  a.payload.recording.courseCode === b.payload.recording.courseCode &&
  a.payload.recording.title === b.payload.recording.title;

// Only the newest position of a recording matters, and none once it's watched.
export function addToQueue(queue, event) {
  const has = (type) => (other) => other.type === type && sameRecording(other, event);
  if (event.type === "recording.progress" && queue.some(has("recording.watched"))) return queue;
  const replaced = event.type === "recording.downloaded" ? "" : "recording.progress";
  return [...queue.filter((other) => !has(replaced)(other)), event].slice(-QUEUE_MAX);
}

export const isWatched = (time, duration) =>
  Number.isFinite(duration) && duration > 0 && time / duration >= WATCHED_FRACTION;
