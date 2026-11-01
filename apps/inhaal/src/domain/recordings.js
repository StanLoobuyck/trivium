// Opnames uit SwiftSkip koppelen aan lessen. Pure functies; zie packages/contract/CONTRACT.md.
import { findCourseByCode } from "./courses.js";
import { codeKey } from "./rooster.js";
import { DONE, isDone, isAlive } from "./sessions.js";

const brusselsDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Brussels" });
const dayOf = (iso) => brusselsDay.format(new Date(iso));

export const recordingKey = (recording) => `${codeKey(recording.courseCode)}|${recording.title ?? recording.recordedOn ?? recording.lectureNumber ?? ""}`;

const hasOtherRecording = (session, key) => (session.recordings ?? []).some((r) => r.key && r.key !== key);

function firstUsable(list, now) {
  const sorted = [...list].sort((a, b) => (a.type !== "lecture") - (b.type !== "lecture") || a.start.localeCompare(b.start));
  return sorted.find((s) => !isDone(s, now)) ?? sorted[0] ?? null;
}

// Volgorde uit het contract: eerder gekozen koppeling, datum, lesnummer. Anders kiest de gebruiker.
export function findSession(recording, { courses, sessions, numbers, now }) {
  const course = findCourseByCode(courses, recording.courseCode);
  if (!course) return { course: null, session: null };
  const key = recordingKey(recording);
  const own = sessions.filter((s) => isAlive(s) && s.courseId === course.id && s.status !== "cancelled");
  const known = own.find((s) => (s.recordings ?? []).some((r) => r.key === key));
  if (known) return { course, session: known };
  const free = own.filter((s) => !hasOtherRecording(s, key));
  if (recording.recordedOn) {
    const session = firstUsable(free.filter((s) => dayOf(s.start) === recording.recordedOn), now);
    if (session) return { course, session };
  }
  if (recording.lectureNumber) {
    // Een les kan uit meerdere opnames bestaan ("Les 6, part 3"), dus hier telt een bestaande opname niet mee.
    const session = own.find((s) => s.type === "lecture" && numbers.get(s.id) === recording.lectureNumber);
    if (session) return { course, session };
  }
  return { course, session: null };
}

function withRecording(session, event, key) {
  const { title, url } = event.payload.recording;
  const list = session.recordings ?? [];
  const old = list.find((r) => r.key === key);
  const manual = old ? [] : list.filter((r) => !r.key);
  const next = { ...manual[0], ...old, key, title };
  if (url && !manual[0]?.url) next.url = url;
  if (event.type === "recording.downloaded") next.fileName = event.payload.fileName;
  return [...list.filter((r) => r !== old && !manual.includes(r)), next];
}

function addUnmatched(unmatched, event, key, course) {
  const entry = unmatched.find((u) => u.key === key);
  const others = (entry?.events ?? []).filter((e) => e.type !== event.type);
  const updated = { key, courseId: course.id, recording: event.payload.recording, events: [...others, event] };
  return entry ? unmatched.map((u) => (u === entry ? updated : u)) : [...unmatched, updated];
}

// Rekent uit wat er moet veranderen; `forced` koppelt een opname aan een les die de gebruiker koos.
export function planRecordings(events, { courses, sessions, numbers, now, unmatched = [], forced = {} }) {
  const working = sessions.map((s) => ({ ...s }));
  const changes = new Map();
  const ticked = new Set();
  let waiting = unmatched;
  const change = (session, fields) => {
    Object.assign(session, fields);
    changes.set(session.id, { ...changes.get(session.id), ...fields });
  };

  for (const event of [...events].sort((a, b) => a.occurredAt.localeCompare(b.occurredAt))) {
    const { recording } = event.payload;
    const key = recordingKey(recording);
    const { course, session: found } = findSession(recording, { courses, sessions: working, numbers, now });
    const session = forced[key] ? working.find((s) => s.id === forced[key]) : found;
    if (!course) continue;
    if (!session) { waiting = addUnmatched(waiting, event, key, course); continue; }

    change(session, { recordings: withRecording(session, event, key) });
    if (event.type === "recording.watched") {
      if (!DONE.has(session.status) && !ticked.has(session.id)) ticked.add(session.id);
    } else if (event.type === "recording.progress" && !isDone(session, now) && !ticked.has(session.id)) {
      change(session, { status: "inProgress", progressSec: event.payload.positionSec });
    }
  }
  return { changes, ticked: [...ticked], unmatched: waiting };
}
