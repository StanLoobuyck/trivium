// State shared between screens. One object, so every module sees reassignments (S.courses = …).
export const S = {
  courses: [],
  setup: null,
  queue: { items: [], notes_paused: false, worker: true },
  lectures: [],
  folders: { folders: [], assign: {} },
  editing: false,  // an inline rename field is open: polled redraws must not replace it
  sem: null,       // /api/semesters: current semester, per course {semester, archived}
};
export const isArchived = (courseId) => !!S.sem?.courses[courseId]?.archived;

const COLORS = ["#3b82f6", "#14b8a6", "#e11d48", "#a3a3a3", "#8b5cf6", "#22c55e", "#eab308", "#06b6d4"];  // no orange: that is the accent
export const courseColor = (id) => COLORS[Math.max(0, S.courses.findIndex((c) => c.id === id)) % COLORS.length];
export const reason = (code) => t("r_" + code, { plan: S.setup?.claude_plan || "" }).replace("  ", " ");
export const courseName = (id) => (S.courses.find((c) => c.id === id) || {}).name || id;
export const courseLang = (id) => (S.courses.find((c) => c.id === id) || {}).language || "nl";
