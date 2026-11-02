// Lokale opslag met Dexie. Elk record krijgt id, createdAt, updatedAt en deletedAt, zodat sync later eenvoudig blijft.
import Dexie from "dexie";

export const db = new Dexie("sequo");
db.version(1).stores({
  semesters: "id, isActive",
  courses: "id, semesterId",
  sessions: "id, courseId, start",
  meta: "key",
});

export const stamp = (record, now = new Date()) => ({
  id: crypto.randomUUID(),
  createdAt: now.toISOString(),
  updatedAt: now.toISOString(),
  deletedAt: null,
  ...record,
});

export async function getMeta(key, fallback = null) {
  return (await db.meta.get(key))?.value ?? fallback;
}

export const setMeta = (key, value) => db.meta.put({ key, value });

export const requestPersistence = () => navigator.storage?.persist?.().catch(() => false);
