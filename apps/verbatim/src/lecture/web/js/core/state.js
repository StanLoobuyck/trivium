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

// The palette of packages/design, in the order Inhaal hands colours out: data-course="<key>" colours the .dot.
const PALETTE = ["blue", "orange", "green", "purple", "pink", "indigo", "yellow", "red"];
export const courseKey = (id) => PALETTE[Math.max(0, S.courses.findIndex((c) => c.id === id)) % PALETTE.length];
export const reason = (code) => t("r_" + code, { plan: S.setup?.claude_plan || "" }).replace("  ", " ");
export const courseName = (id) => (S.courses.find((c) => c.id === id) || {}).name || id;
export const courseLang = (id) => (S.courses.find((c) => c.id === id) || {}).language || "nl";
