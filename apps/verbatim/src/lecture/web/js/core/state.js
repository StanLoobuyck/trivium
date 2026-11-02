// State shared between screens. One object, so every module sees reassignments (S.courses = …).
export const S = {
  courses: [],
  setup: null,
  queue: { items: [], notes_paused: false, worker: true },
  lectures: [],
  folders: { folders: [], assign: {} },
  editing: false,  // an inline rename field is open: polled redraws must not replace it
  sem: null,       // /api/semesters: current semester, per course {semester, archived}
  colors: (() => { try { return JSON.parse(localStorage.getItem("lt-colors")) || {}; } catch { return {}; } })(),
};
export const isArchived = (courseId) => !!S.sem?.courses[courseId]?.archived;

// The palette of packages/design, in the order Inhaal hands colours out: data-course="<key>" colours the .dot.
const PALETTE = ["blue", "orange", "green", "purple", "pink", "indigo", "yellow", "red"];
// Inhaal's colour when the hub gave one; remembered, so the colours are right before the hub answers.
export const courseKey = (id) => S.colors[id] || PALETTE[Math.max(0, S.courses.findIndex((c) => c.id === id)) % PALETTE.length];
export const sortedCourses = () => [...S.courses].sort((a, b) => a.name.localeCompare(b.name, "nl", { sensitivity: "base", numeric: true }));
export const reason = (code) => t("r_" + code, { plan: S.setup?.claude_plan || "" }).replace("  ", " ");
export const courseName = (id) => (S.courses.find((c) => c.id === id) || {}).name || id;
export const courseLang = (id) => (S.courses.find((c) => c.id === id) || {}).language || "nl";
