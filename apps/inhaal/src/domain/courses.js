// Vakken voorstellen uit roosterlessen. Pure functies.
import { codeKey } from "./rooster.js";

export const COLORS = ["blue", "orange", "green", "purple", "pink", "indigo", "yellow", "red"];

const SMALL = new Set(["en", "van", "de", "het", "voor", "and", "of", "the", "for"]);
export const nameKey = (name) => name.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();

export function shortName(name) {
  const words = nameKey(name).split(" ").filter((w) => !SMALL.has(w));
  if (words.length === 1) return name.slice(0, 3).toUpperCase();
  return words.map((w) => w[0]).join("").toUpperCase().slice(0, 4);
}

const median = (values) => {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
};
const minutes = (e) => Math.round((new Date(e.end) - new Date(e.start)) / 60000);

// Hoorcollege en oefenzitting hebben elk een code; de vaknaam brengt ze samen.
export function proposeCourses(events) {
  const groups = new Map();
  for (const event of events) {
    const key = nameKey(event.name);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(event);
  }
  return [...groups.values()].map((group, order) => {
    const lectures = group.filter((e) => e.type === "lecture");
    const practice = group.filter((e) => e.type === "exercise" || e.type === "lab");
    const name = group[0].name;
    return {
      name,
      shortName: shortName(name),
      codes: [...new Set(group.map((e) => e.code))],
      colorKey: COLORS[order % COLORS.length],
      order,
      language: group.some((e) => e.english) ? "en" : "nl",
      lecturer: [...new Set(group.flatMap((e) => e.lecturers))].join(", ") || null,
      minutesPerLecture: median(lectures.map(minutes)) || 120,
      minutesPerExercise: median(practice.map(minutes)) || 150,
      hidden: group.every((e) => e.type === "project" || e.type === "excursion"),
    };
  });
}

// Vervolgvakken (EBS → EBS+): dezelfde docent en lessen die elkaar in de tijd niet overlappen.
export function proposeMerges(proposals, events) {
  const range = (course) => {
    const keys = new Set(course.codes.map(codeKey));
    const own = events.filter((e) => keys.has(codeKey(e.code)) && e.type === "lecture");
    return own.length ? [own[0].start, own.at(-1).end, own[0].lecturers[0]] : null;
  };
  const merges = [];
  proposals.forEach((a, i) => {
    proposals.slice(i + 1).forEach((b) => {
      const ra = range(a);
      const rb = range(b);
      if (!ra || !rb || !ra[2] || ra[2] !== rb[2]) return;
      if (ra[1] <= rb[0] || rb[1] <= ra[0]) merges.push([a.name, b.name]);
    });
  });
  return merges;
}

export function mergeProposal(proposals, keepName, otherName) {
  const keep = proposals.find((c) => c.name === keepName);
  const other = proposals.find((c) => c.name === otherName);
  const merged = { ...keep, codes: [...keep.codes, ...other.codes], lecturer: keep.lecturer ?? other.lecturer };
  return proposals.filter((c) => c !== other).map((c) => (c === keep ? merged : c));
}

export function findCourseByCode(courses, code) {
  const key = codeKey(code);
  return courses.find((c) => !c.deletedAt && c.codes.some((x) => codeKey(x) === key));
}
