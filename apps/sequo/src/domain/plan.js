// Inhaalplan en achterstand per lesweek. Pure functies; niets hiervan wordt opgeslagen.
import { effectiveStatus, isOpen, sessionMinutes } from "./sessions.js";

const DAY = 86400000;

// Lessen die nog komen, tot de examens: ook die moet je nog zien of bijwonen.
export function comingWork(sessions, courses, examStart, now) {
  const exam = new Date(`${examStart}T00:00:00`);
  const byId = new Map(courses.map((c) => [c.id, c]));
  const coming = sessions.filter((s) => effectiveStatus(s, now) === "upcoming" && new Date(s.start) < exam);
  return { count: coming.length, minutes: coming.reduce((sum, s) => sum + sessionMinutes(s, byId.get(s.courseId)), 0) };
}

export function catchUpPlan({ minutes, comingMinutes = 0, examStart, speed = 1, now }) {
  const exam = new Date(`${examStart}T00:00:00`);
  const days = Math.ceil((exam - now) / DAY);
  const watchMinutes = (minutes + comingMinutes) / speed;
  if (days <= 0) return { watchMinutes, weeks: 0, perWeekMinutes: null };
  const weeks = Math.ceil(days / 7);
  return { watchMinutes, weeks, perWeekMinutes: watchMinutes / weeks };
}

function mondayOf(value) {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return date;
}

// Hoeveel lessen uit elke lesweek nog openstaan, van de eerste week tot nu. Weken zonder les blijven zichtbaar als 0.
export function backlogByWeek(sessions, startDate, now) {
  const weeks = [];
  const last = mondayOf(now);
  for (let week = mondayOf(`${startDate}T12:00:00`); week <= last; week = new Date(week.getFullYear(), week.getMonth(), week.getDate() + 7)) {
    weeks.push({ start: week, open: 0 });
  }
  for (const session of sessions) {
    if (!isOpen(session, now)) continue;
    const start = mondayOf(session.start).getTime();
    const entry = weeks.find((w) => w.start.getTime() === start);
    if (entry) entry.open += 1;
  }
  return weeks;
}
