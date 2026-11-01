// Plak-import uit Notes en export in hetzelfde formaat.
import { nameKey } from "./courses.js";
import { isAlive, isDone } from "./sessions.js";

const HEADINGS = [[/^hoorcolleges?$/i, "lecture"], [/^oefenzittingen?$/i, "exercise"], [/^(practica|labo'?s?)$/i, "lab"]];

export function parseNotes(text) {
  const items = [];
  let type = null;
  let course = null;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const check = line.match(/^(?:[-*•]\s*)?\[( |x|X)\]\s*(\d{1,2})\/(\d{1,2})/);
    if (check) {
      if (type && course) items.push({ type, course, day: +check[2], month: +check[3], checked: check[1] !== " " });
      continue;
    }
    const heading = HEADINGS.find(([re]) => re.test(line));
    if (heading) { type = heading[1]; course = null; continue; }
    if (line.endsWith(":")) course = line.slice(0, -1).trim();
  }
  return items;
}

function distance(a, b) {
  let row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const next = [i];
    for (let j = 1; j <= b.length; j++) {
      next[j] = Math.min(row[j] + 1, next[j - 1] + 1, row[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    row = next;
  }
  return row[b.length];
}

// Vangt tikfouten op, bv. "Elektrische Basischakelingen" voor "Elektronische basisschakelingen".
export function matchCourse(name, courses) {
  const key = nameKey(name);
  let best = null;
  let score = Infinity;
  for (const course of courses.filter((c) => isAlive(c) && !c.hidden)) {
    const candidates = [course.name, course.shortName].map(nameKey);
    for (const candidate of candidates) {
      const d = distance(key, candidate) / Math.max(key.length, candidate.length);
      if (d < score) { score = d; best = course; }
    }
  }
  return score <= 0.35 ? best : null;
}

const localDay = (iso) => {
  const d = new Date(iso);
  return `${d.getDate()}/${d.getMonth() + 1}`;
};

export function planNotesImport(items, courses, sessions, semester) {
  const year = (month) => {
    const start = new Date(`${semester.startDate}T12:00:00`);
    return month - 1 < start.getMonth() - 1 ? start.getFullYear() + 1 : start.getFullYear();
  };
  const plan = { link: [], create: [], unknown: [] };
  const used = new Set();
  for (const item of items) {
    const course = matchCourse(item.course, courses);
    if (!course) { plan.unknown.push(item.course); continue; }
    const session = sessions.find((s) => isAlive(s) && !used.has(s.id) && s.courseId === course.id && s.type === item.type
      && localDay(s.start) === `${item.day}/${item.month}`);
    if (session) {
      used.add(session.id);
      plan.link.push({ id: session.id, checked: item.checked });
    } else {
      const minutes = item.type === "lecture" ? course.minutesPerLecture : course.minutesPerExercise;
      const start = new Date(year(item.month), item.month - 1, item.day, 9, 0);
      plan.create.push({
        courseId: course.id,
        type: item.type,
        start: start.toISOString(),
        end: new Date(start.getTime() + minutes * 60000).toISOString(),
        checked: item.checked,
      });
    }
  }
  plan.unknown = [...new Set(plan.unknown)];
  return plan;
}

export function toNotes(courses, sessions, now) {
  const pad = (n) => String(n).padStart(2, "0");
  const section = (title, type) => {
    const blocks = courses.filter((c) => isAlive(c) && !c.hidden).flatMap((course) => {
      const own = sessions.filter((s) => isAlive(s) && s.courseId === course.id && s.type === type
        && !["upcoming", "cancelled"].includes(s.status === "upcoming" && new Date(s.end) <= now ? "missed" : s.status))
        .sort((a, b) => a.start.localeCompare(b.start));
      if (!own.length) return [];
      return [`${course.name}:`, ...own.map((s) => {
        const d = new Date(s.start);
        return `- [${isDone(s, now) ? "x" : " "}] ${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
      }), ""];
    });
    return blocks.length ? [title, ...blocks] : [];
  };
  return [...section("Hoorcolleges", "lecture"), ...section("Oefenzittingen", "exercise"), ...section("Practica", "lab")].join("\n").trim();
}
