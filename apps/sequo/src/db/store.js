// De toestand van de app: laden, wijzigen en bij elke wijziging de schermen verwittigen.
import { findCourseByCode, proposeCourses } from "../domain/courses.js";
import { mergeRooster } from "../domain/merge.js";
import { planRecordings, reconcileNotes } from "../domain/recordings.js";
import { pickActiveSemester } from "../domain/semesters.js";
import { computeNumbers } from "../domain/sessions.js";
import { db, getMeta, requestPersistence, setMeta, stamp } from "./index.js";

export const state = { semester: null, semesters: [], courses: [], sessions: [], meta: {} };
const nowIso = () => new Date().toISOString();

export async function load() {
  state.semesters = await db.semesters.toArray();
  const { active, stale } = pickActiveSemester(state.semesters);
  // Verouderde actieve semesters (van een ander toestel) uitzetten; de sync brengt dat naar de andere toestellen.
  if (stale.length) {
    const now = nowIso();
    await db.semesters.bulkPut(stale.map((s) => ({ ...s, isActive: false, updatedAt: now })));
    state.semesters = await db.semesters.toArray();
  }
  state.semester = state.semesters.find((s) => s.id === active?.id) ?? null;
  const id = state.semester?.id;
  state.courses = id ? (await db.courses.where({ semesterId: id }).toArray()).filter((c) => !c.deletedAt).sort((a, b) => a.order - b.order) : [];
  const ids = state.courses.map((c) => c.id);
  state.sessions = (await db.sessions.where("courseId").anyOf(ids).toArray()).filter((s) => !s.deletedAt);
  const firstUse = await getMeta("firstUseAt");
  state.meta = {
    firstUseAt: firstUse,
    lastBackupAt: await getMeta("lastBackupAt"),
    lastCourseId: await getMeta("lastCourseId"),
    installDismissed: await getMeta("installDismissed", false),
    weeksDismissed: await getMeta("weeksDismissed", false),
    unmatchedRecordings: await getMeta("unmatchedRecordings", []),
  };
}

export const courseById = (id) => state.courses.find((c) => c.id === id);
export const sessionById = (id) => state.sessions.find((s) => s.id === id);

function sessionFromEvent(event, courseId, now) {
  return stamp({
    id: event.uid, courseId, code: event.code, type: event.type, start: event.start, end: event.end,
    status: "upcoming", statusChangedAt: null, source: "rooster", roosterUid: event.uid,
    location: event.location || null, online: event.online, recordings: [], note: null, progressSec: null, verbatimJob: null,
  }, now);
}

export async function createSemester({ semester, courses, events }) {
  const now = new Date();
  await db.transaction("rw", db.semesters, db.courses, db.sessions, db.meta, async () => {
    await db.semesters.toCollection().modify({ isActive: false, updatedAt: now.toISOString() });
    const saved = stamp({ ...semester, isActive: true, roosterSource: "upload" }, now);
    await db.semesters.add(saved);
    const records = courses.map((c) => stamp({ ...c, semesterId: saved.id }, now));
    await db.courses.bulkAdd(records);
    await db.sessions.bulkPut(events.map((e) => sessionFromEvent(e, findCourseByCode(records, e.code).id, now)));
    if (!(await getMeta("firstUseAt"))) await setMeta("firstUseAt", now.toISOString());
  });
  requestPersistence();
  await load();
}

// Volgende uploads: alleen toevoegen en wijzigen. Verdwenen lessen komen terug als voorstel.
export async function applyRooster(events) {
  const now = new Date();
  const { add, update, vanished } = mergeRooster(state.sessions, events);
  await db.transaction("rw", db.semesters, db.courses, db.sessions, async () => {
    const unknown = add.filter((e) => !findCourseByCode(state.courses, e.code));
    const records = proposeCourses(unknown).map((c, i) => stamp({
      ...c, semesterId: state.semester.id, order: state.courses.length + i,
    }, now));
    await db.courses.bulkAdd(records);
    const all = [...state.courses, ...records];
    await db.sessions.bulkPut(add.map((e) => sessionFromEvent(e, findCourseByCode(all, e.code).id, now)));
    await Promise.all(update.map(({ id, ...changes }) => db.sessions.update(id, { ...changes, updatedAt: now.toISOString() })));
    const last = events.at(-1)?.end.slice(0, 10);
    if (last > state.semester.endDate) await db.semesters.update(state.semester.id, { endDate: last, updatedAt: now.toISOString() });
  });
  await load();
  return { added: add.length, updated: update.length, vanished };
}

// Het geheugen verandert meteen, zodat het scherm niet op de opslag hoeft te wachten.
export async function updateSession(id, changes) {
  Object.assign(sessionById(id) ?? {}, changes);
  await db.sessions.update(id, { ...changes, updatedAt: nowIso() });
}

export async function setStatus(ids, status) {
  const time = nowIso();
  const before = ids.map((id) => ({ id, status: sessionById(id).status, statusChangedAt: sessionById(id).statusChangedAt }));
  await Promise.all(ids.map((id) => updateSession(id, { status, statusChangedAt: time })));
  return async () => {
    await Promise.all(before.map(({ id, ...old }) => updateSession(id, old)));
  };
}

async function applyRecordingPlan(events, forced = {}, unmatched = state.meta.unmatchedRecordings) {
  const now = new Date();
  const plan = planRecordings(events, {
    courses: state.courses, sessions: state.sessions, numbers: computeNumbers(state.sessions), now, unmatched, forced,
  });
  await Promise.all([...plan.changes].map(([id, changes]) => updateSession(id, changes)));
  const undo = plan.ticked.length ? await setStatus(plan.ticked, "watched") : null;
  await setMeta("unmatchedRecordings", plan.unmatched);
  state.meta.unmatchedRecordings = plan.unmatched;
  return { ticked: plan.ticked, undo };
}

// Wat Velox stuurt, kan dubbel aankomen: de wachtrij wordt pas na de bevestiging geleegd.
export async function ingestRecordings(events) {
  const seen = await getMeta("seenEvents", []);
  const known = new Set(seen);
  const fresh = events.filter((e) => !known.has(e.id));
  const result = await applyRecordingPlan(fresh);
  await setMeta("seenEvents", [...seen, ...fresh.map((e) => e.id)].slice(-1000));
  return result;
}

// Zet de badges van Verbatim op de juiste les, ook als de lesnummers intussen verschoven zijn.
export async function reconcileVerbatim(events) {
  const changes = reconcileNotes(events, {
    courses: state.courses, sessions: state.sessions, numbers: computeNumbers(state.sessions), now: new Date(),
  });
  await Promise.all([...changes].map(([id, fields]) => updateSession(id, fields)));
}

export async function chooseRecording(key, sessionId) {
  const entry = state.meta.unmatchedRecordings.find((u) => u.key === key);
  const others = state.meta.unmatchedRecordings.filter((u) => u !== entry);
  return applyRecordingPlan(entry.events, { [key]: sessionId }, others);
}

export async function dropRecording(key) {
  state.meta.unmatchedRecordings = state.meta.unmatchedRecordings.filter((u) => u.key !== key);
  await setMeta("unmatchedRecordings", state.meta.unmatchedRecordings);
}

export async function deleteSession(id) {
  await db.sessions.update(id, { deletedAt: nowIso(), updatedAt: nowIso() });
  await load();
  return async () => {
    await db.sessions.update(id, { deletedAt: null, updatedAt: nowIso() });
    await load();
  };
}

export async function addManualSessions({ courseId, type, dates, minutes }) {
  const now = new Date();
  await db.sessions.bulkAdd(dates.map((end) => stamp({
    courseId, code: null, type,
    start: new Date(end.getTime() - minutes * 60000).toISOString(), end: end.toISOString(),
    status: "upcoming", statusChangedAt: null, source: "manueel", roosterUid: null,
    location: null, online: false, recordings: [], note: null, progressSec: null, verbatimJob: null,
  }, now)));
  await setMeta("lastCourseId", courseId);
  await load();
}

export async function updateCourse(id, changes) {
  await db.courses.update(id, { ...changes, updatedAt: nowIso() });
  await load();
}

export async function updateSemester(changes) {
  await db.semesters.update(state.semester.id, { ...changes, updatedAt: nowIso() });
  await load();
}

export async function setAllDurations(changes) {
  await Promise.all(state.courses.map((c) => db.courses.update(c.id, { ...changes, updatedAt: nowIso() })));
  await load();
}

export async function mergeCourses(keepId, otherId) {
  const keep = courseById(keepId);
  const other = courseById(otherId);
  const time = nowIso();
  await db.transaction("rw", db.courses, db.sessions, async () => {
    await db.sessions.where({ courseId: otherId }).modify({ courseId: keepId, updatedAt: time });
    await db.courses.update(keepId, { codes: [...keep.codes, ...other.codes], updatedAt: time });
    await db.courses.update(otherId, { deletedAt: time, updatedAt: time });
  });
  await load();
}

export async function splitCode(courseId, code) {
  const course = courseById(courseId);
  const now = new Date();
  const name = `${course.name} (${code})`;
  const record = stamp({ ...course, id: undefined, name, codes: [code], order: state.courses.length }, now);
  record.id = crypto.randomUUID();
  await db.transaction("rw", db.courses, db.sessions, async () => {
    await db.courses.add(record);
    await db.courses.update(courseId, { codes: course.codes.filter((c) => c !== code), updatedAt: now.toISOString() });
    await db.sessions.where({ courseId }).filter((s) => s.code === code).modify({ courseId: record.id, updatedAt: now.toISOString() });
  });
  await load();
}

export async function applyNotesPlan(plan) {
  const now = new Date();
  await db.transaction("rw", db.sessions, async () => {
    for (const { id, checked } of plan.link) {
      if (checked) await db.sessions.update(id, { status: "watched", statusChangedAt: now.toISOString(), updatedAt: now.toISOString() });
    }
    await db.sessions.bulkAdd(plan.create.map(({ checked, ...s }) => stamp({
      ...s, code: null, status: checked ? "watched" : "upcoming", statusChangedAt: null, source: "manueel", roosterUid: null,
      location: null, online: false, recordings: [], note: null, progressSec: null, verbatimJob: null,
    }, now)));
  });
  await load();
}

export async function dumpAll() {
  return { semesters: await db.semesters.toArray(), courses: await db.courses.toArray(), sessions: await db.sessions.toArray() };
}

// Wissen en herstellen zijn zachte wijzigingen, zodat ze via de hub ook de andere toestellen bereiken.
async function softDeleteAll(keep = new Set()) {
  const time = nowIso();
  await Promise.all([db.semesters, db.courses, db.sessions].map((table) =>
    table.filter((r) => !r.deletedAt && !keep.has(r.id)).modify({ deletedAt: time, updatedAt: time })));
}

export async function restoreAll({ semesters, courses, sessions }) {
  const time = nowIso();
  const touch = (records) => records.map((r) => ({ ...r, updatedAt: time }));
  await db.transaction("rw", db.semesters, db.courses, db.sessions, async () => {
    await softDeleteAll(new Set([...semesters, ...courses, ...sessions].map((r) => r.id)));
    await db.semesters.bulkPut(touch(semesters));
    await db.courses.bulkPut(touch(courses));
    await db.sessions.bulkPut(touch(sessions));
  });
  await markBackup();
}

export async function markBackup() {
  await setMeta("lastBackupAt", nowIso());
  await load();
}

export async function dismiss(key) {
  await setMeta(key, true);
  await load();
}

export async function eraseAll() {
  await softDeleteAll();
  await db.meta.bulkDelete(["firstUseAt", "lastBackupAt", "lastCourseId", "installDismissed", "weeksDismissed", "unmatchedRecordings", "seenEvents"]);
  await load();
}
