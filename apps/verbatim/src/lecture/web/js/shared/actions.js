// Actions used from more than one screen.
import { api, post } from "../core/api.js";
import { S } from "../core/state.js";
import { toast } from "../core/ui.js";
import { refreshDashboard } from "../screens/dashboard.js";
import { renderSetup } from "../screens/setup.js";

export async function startWorker() {
  try { await post("/api/worker/start"); } catch (e) { toast(e.message, true); }
  setTimeout(() => (location.hash.startsWith("#/setup") ? renderSetup() : refreshDashboard()), 900);
}

export async function renameLecture(id, title) {
  await post(`/api/lectures/${encodeURIComponent(id)}/rename`, { title });
  const l = S.lectures.find((x) => x.id === id);
  if (l) l.title = title;
}

// `title` for the confirm question when the lecture isn't in the library list (the lecture page passes it)
export async function deleteLecture(id, title = null) {
  const l = S.lectures.find((x) => x.id === id) || { title: title || id };
  if (!confirm(t("delete_lecture_confirm", { title: l.title }))) return false;
  try { await api(`/api/lectures/${encodeURIComponent(id)}`, { method: "DELETE" }); }
  catch (e) { toast(e.message, true); return false; }
  toast(t("lecture_deleted"));
  return true;
}

// Archive or bring back a course, keeping the stored flag as "automatic" as possible: a past-semester
// course is archived by itself (null), a current one needs archived: true; bringing back is the reverse.
export async function setCourseArchived(courseId, archive) {
  const info = S.sem?.courses[courseId];
  const past = info && S.sem && info.semester < S.sem.current;
  const value = archive ? (past ? null : true) : (past ? false : null);
  await post(`/api/courses/${encodeURIComponent(courseId)}/archived`, { archived: value });
}
