// Back-up als JSON. De versie maakt latere migraties mogelijk.
export const BACKUP_VERSION = 1;

export function toBackup({ semesters, courses, sessions }, now) {
  return { app: "sequo", version: BACKUP_VERSION, exportedAt: now.toISOString(), semesters, courses, sessions };
}

export function readBackup(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("invalid");
  }
  const lists = [data?.semesters, data?.courses, data?.sessions];
  if (data?.app !== "sequo" || data.version !== BACKUP_VERSION || !lists.every(Array.isArray)) throw new Error("invalid");
  return { semesters: data.semesters, courses: data.courses, sessions: data.sessions };
}
