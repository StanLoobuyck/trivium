// Status, nummering en afgeleide waarden. Niets hiervan wordt opgeslagen.
export const COUNTED_TYPES = ["lecture", "exercise", "lab"];
export const OPEN = new Set(["missed", "inProgress"]);
export const DONE = new Set(["watched", "processed", "attended", "skipped"]);

export const isAlive = (record) => !record.deletedAt;

export function effectiveStatus(session, now) {
  if (session.status !== "upcoming") return session.status;
  return new Date(session.end) <= now ? "missed" : "upcoming";
}

export const isOpen = (session, now) => OPEN.has(effectiveStatus(session, now));
export const isDone = (session, now) => DONE.has(effectiveStatus(session, now));

// Per vak en type chronologisch, over alle codes van het vak; geschrapt telt niet mee.
export function computeNumbers(sessions) {
  const counters = new Map();
  const numbers = new Map();
  const sorted = sessions.filter(isAlive).sort((a, b) => a.start.localeCompare(b.start));
  for (const session of sorted) {
    if (session.status === "cancelled" || !COUNTED_TYPES.includes(session.type)) continue;
    const key = `${session.courseId}|${session.type}`;
    const number = (counters.get(key) ?? 0) + 1;
    counters.set(key, number);
    numbers.set(session.id, number);
  }
  return numbers;
}

export function sessionMinutes(session, course) {
  const whole = session.type === "lecture" ? course.minutesPerLecture : course.minutesPerExercise;
  const watched = (session.progressSec ?? 0) / 60;
  return Math.max(0, whole - watched);
}

export function visibleSessions(courses, sessions) {
  const shown = new Map(courses.filter((c) => isAlive(c) && !c.hidden).map((c) => [c.id, c]));
  return sessions.filter((s) => isAlive(s) && shown.has(s.courseId) && COUNTED_TYPES.includes(s.type));
}

export function summarize(courses, sessions, now) {
  const visible = visibleSessions(courses, sessions);
  const byId = new Map(courses.map((c) => [c.id, c]));
  const open = visible.filter((s) => isOpen(s, now)).sort((a, b) => a.start.localeCompare(b.start));
  const done = visible.filter((s) => isDone(s, now));
  const minutes = open.reduce((sum, s) => sum + sessionMinutes(s, byId.get(s.courseId)), 0);

  const perCourse = courses.filter((c) => isAlive(c) && !c.hidden).map((course) => {
    const own = open.filter((s) => s.courseId === course.id);
    const counts = (type) => own.filter((s) => s.type === type).length;
    return {
      course,
      open: own.length,
      lecture: counts("lecture"),
      exercise: counts("exercise"),
      lab: counts("lab"),
      done: done.filter((s) => s.courseId === course.id).length,
    };
  }).sort((a, b) => (a.open === 0) - (b.open === 0) || a.course.order - b.course.order);

  const total = open.length + done.length;
  return { open: open.length, minutes, next: open[0] ?? null, openSessions: open, done: done.length, progress: total ? done.length / total : 0, perCourse };
}

export function needsBackupReminder(lastBackupAt, firstUseAt, now) {
  const since = new Date(lastBackupAt ?? firstUseAt);
  return now - since >= 30 * 86400000;
}
