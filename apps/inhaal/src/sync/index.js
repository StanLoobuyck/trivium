// Sync met de hub: een aparte laag die niets aan de schermen verandert. Alleen actief op het adres van de hub.
import { currentCluster, parseRooster, splitSemesters } from "../domain/rooster.js";
import { db, getMeta, setMeta } from "../db/index.js";
import * as store from "../db/store.js";

const TABLES = ["semesters", "courses", "sessions"];
const POLL_MS = 4000;
const NUDGE_MS = 800;

export const sync = { available: false, status: "off", pending: 0, lastAt: null };

let code = null;
let running = false;
let again = false;
let nudgeTimer;
let onChange = () => {};
let onRooster = () => {};
let onStatus = () => {};

async function pendingChanges() {
  const since = await getMeta("lastPushAt", "");
  const lists = await Promise.all(TABLES.map(async (table) =>
    (await db[table].toArray()).filter((r) => r.updatedAt > since).map((record) => ({ table, record }))));
  return lists.flat();
}

async function request(path, options = {}) {
  const response = await fetch(`./api/${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${code}`, "Content-Type": "application/json" },
  });
  if (response.status === 401) throw new Error("code");
  if (!response.ok) throw new Error("hub");
  return response.json();
}

// Conflicten per record: de recentste updatedAt wint, ook aan deze kant.
async function applyRemote(records) {
  let changed = false;
  await db.transaction("rw", db.semesters, db.courses, db.sessions, async () => {
    for (const { table, record } of records) {
      if (!TABLES.includes(table)) continue;
      const local = await db[table].get(record.id);
      if (local && local.updatedAt >= record.updatedAt) continue;
      await db[table].put(record);
      changed = true;
    }
  });
  return changed;
}

async function refreshRooster(hash) {
  if (!hash || !store.state.semester || hash === (await getMeta("roosterHash"))) return;
  const { text } = await request("rooster");
  const events = parseRooster(text);
  const cluster = currentCluster(splitSemesters(events), new Date());
  const result = await store.applyRooster(cluster);
  await setMeta("roosterHash", hash);
  onRooster(result);
}

// Berichten van Verbatim. Elk toestel haalt ze zelf op; de cursor blijft lokaal.
async function fetchEvents() {
  const after = await getMeta("eventCursor", 0);
  const answer = await request(`events?after=${after}`).catch(() => null);
  if (!answer) return; // een bericht dat niet aankomt, breekt niets: de gewone sync gaat gewoon door
  const { events, cursor } = answer;
  if (!events.length) return;
  if (store.state.semester) {
    await store.ingestRecordings(events);
    onChange();
  }
  await setMeta("eventCursor", cursor);
}

function setStatus(status) {
  sync.status = status;
  onStatus();
}

async function run() {
  if (!code) return;
  if (running) { again = true; return; }
  running = true;
  try {
    const startedAt = new Date().toISOString();
    const changes = await pendingChanges();
    sync.pending = changes.length;
    const cursor = await getMeta("cursor", 0);
    const result = await request("sync", { method: "POST", body: JSON.stringify({ cursor, changes }) });
    await setMeta("lastPushAt", startedAt);
    const changed = await applyRemote(result.records);
    await setMeta("cursor", result.cursor);
    if (changed) {
      await store.load();
      onChange();
    }
    await refreshRooster(result.rooster);
    await fetchEvents();
    sync.pending = 0;
    sync.lastAt = new Date();
    setStatus("ok");
  } catch (error) {
    setStatus(error.message === "code" ? "badCode" : "offline");
  } finally {
    running = false;
    if (again) { again = false; run(); }
  }
}

export function nudge() {
  clearTimeout(nudgeTimer);
  nudgeTimer = setTimeout(run, NUDGE_MS);
}

export async function connect(newCode) {
  code = newCode.trim();
  await setMeta("syncCode", code);
  await run();
  return sync.status === "ok";
}

export async function startSync(handlers) {
  ({ onChange, onRooster, onStatus } = handlers);
  try {
    const response = await fetch("./api/health");
    sync.available = response.ok && (await response.json()).app === "inhaal-hub";
  } catch {
    sync.available = false;
  }
  if (!sync.available) return;
  code = await getMeta("syncCode");
  onStatus();
  run();
  setInterval(() => { if (!document.hidden) run(); }, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) run(); });
  window.addEventListener("online", run);
}
