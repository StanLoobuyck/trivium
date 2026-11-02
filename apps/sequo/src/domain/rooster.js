// De TimeEdit-export van KU Leuven lezen. Pure functies, zonder UI.
import ICAL from "ical.js";

const GROUP = /^\d?[A-Z]?[a-z]*\d*[A-Za-z]*\/[A-Z]\d+$|^\d[A-Z]\w+$/;

export function codeKey(code) {
  return code.replace(/\s+/g, "").toUpperCase();
}

function classify(category, word, name) {
  const w = word.toLowerCase();
  if (/^p&o\b/i.test(name)) return "project";
  if (/^07/.test(category) || /excursie|excursion/.test(w)) return "excursion";
  if (/^(hoorcollege|lecture)/.test(w)) return "lecture";
  if (/^(oefening|exercise)/.test(w)) return "exercise";
  if (/^(practic|laborator|labo)/.test(w)) return "lab";
  return /^01/.test(category) ? "lecture" : "exercise";
}

// SUMMARY = "<code> <naam>: <type>, <docent>, <groep>", soms zonder type en met komma's in de naam.
export function parseSummary(summary, description = "") {
  const clean = summary.replace(/\s+/g, " ").trim();
  const space = clean.indexOf(" ");
  const code = clean.slice(0, space);
  const rest = clean.slice(space + 1);
  const category = description.split("\n")[0].trim();

  const colon = rest.indexOf(": ");
  const segments = (colon >= 0 ? rest.slice(colon + 2) : rest).split(", ").map((s) => s.trim());
  const word = colon >= 0 ? segments.shift() : "";

  const trailing = () => segments.length > (colon >= 0 ? 0 : 1);
  while (trailing() && (segments.at(-1) === "Online" || GROUP.test(segments.at(-1)))) segments.pop();

  let name;
  let lecturers;
  if (colon >= 0) {
    name = rest.slice(0, colon);
    lecturers = segments;
  } else {
    lecturers = segments.length > 1 ? [segments.pop()] : [];
    name = segments.join(", ");
  }
  lecturers = lecturers.filter((l) => l !== "geen docent");
  return { code, name, lecturers, type: classify(category, word, name), english: /^(lecture|exercises|laboratory)/i.test(word) };
}

export function parseRooster(text) {
  const root = new ICAL.Component(ICAL.parse(text));
  return root.getAllSubcomponents("vevent").map((component) => {
    const event = new ICAL.Event(component);
    const location = (event.location ?? "").split("\n").map((l) => l.trim()).filter(Boolean).join(" + ");
    return {
      uid: event.uid,
      start: event.startDate.toJSDate().toISOString(),
      end: event.endDate.toJSDate().toISOString(),
      location,
      online: /^online\b/i.test(location),
      ...parseSummary(event.summary ?? "", event.description ?? ""),
    };
  }).sort((a, b) => a.start.localeCompare(b.start));
}

// Een export bevat meerdere semesters; een gat van meer dan drie weken scheidt ze.
export function splitSemesters(events, gapDays = 21) {
  const clusters = [];
  for (const event of events) {
    const last = clusters.at(-1)?.at(-1);
    if (last && new Date(event.start) - new Date(last.end) <= gapDays * 86400000) clusters.at(-1).push(event);
    else clusters.push([event]);
  }
  return clusters;
}

export function currentCluster(clusters, now) {
  const time = now.getTime();
  return clusters.find((c) => new Date(c.at(-1).end).getTime() >= time) ?? clusters.at(-1) ?? [];
}

function mondayOf(date) {
  const d = new Date(date);
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d;
}

const day = (d) => {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

// Voorinstelling KU Leuven: semester 1 begint rond 21 september, semester 2 rond 8 februari.
export function proposeSemester(cluster) {
  const first = new Date(cluster[0].start);
  const last = new Date(cluster.at(-1).end);
  const autumn = first.getMonth() >= 7;
  const year = first.getFullYear();
  const preset = mondayOf(autumn ? new Date(year, 8, 24) : new Date(year, 1, 11));
  const firstMonday = mondayOf(first);
  const startDate = day(preset < firstMonday ? preset : firstMonday);
  const exam = mondayOf(last);
  exam.setDate(exam.getDate() + (autumn ? 21 : 14));
  return {
    name: `${autumn ? 1 : 2}e semester ${autumn ? `${year}-${year + 1}` : `${year - 1}-${year}`}`,
    startDate,
    endDate: day(last),
    examStart: day(exam),
  };
}

// Aantal volledige lesweken tussen de semesterstart en de eerste les in het rooster.
export function missingWeeks(startDate, sessions) {
  if (!sessions.length) return 0;
  const first = sessions.map((s) => s.start).sort()[0];
  const days = (mondayOf(first) - mondayOf(`${startDate}T12:00:00`)) / 86400000;
  return Math.max(0, Math.round(days / 7));
}
