// Home = the library: what's in progress + all lectures (or one course / folder). Polled every 3 s.
import { api, post } from "../core/api.js";
import { $, $$, view } from "../core/dom.js";
import { esc } from "../core/format.js";
import { S, courseKey, courseName } from "../core/state.js";
import { drawSidebar, markSideLoaded } from "../core/sidebar.js";
import { paint, poll, toast } from "../core/ui.js";
import { progressHtml, statusText } from "../shared/jobstatus.js";
import { drawLibrary, setLibrarySel } from "./library.js";

// sel: "" (all), "c:<course>" or "f:<folder>"; focus = "progress" scrolls to the in-progress list
export async function renderDashboard(sel = "", focus = null) {
  setLibrarySel(sel);
  view.innerHTML = `
    <h1 class="large-title" id="lib-title"></h1>
    <nav class="chips narrow-only" id="lib-chips" aria-label="${t("nav_courses")}"></nav>
    <div class="overview">
      <div class="overview-side flow"><section id="lib-hero"></section><section id="jobs-wrap"></section></div>
      <div class="overview-main flow"><section class="stack-tight" id="lib-tools"></section><section id="lib-wrap"></section></div>
      <div class="overview-extra flow" id="lib-actions"></div>
    </div>`;
  await refreshDashboard();
  if (focus === "progress") $("#jobs-wrap")?.scrollIntoView({ block: "start" });
  poll(refreshDashboard, 3000);
}

export async function refreshDashboard() {
  const [s, q, l, f, sem, inbox] = await Promise.all([api("/api/setup"), api("/api/queue"), api("/api/lectures"),
    api("/api/folders"), api("/api/semesters"),
    api("/api/inbox").catch(() => null)]).catch((e) => { toast(e.message, true); return []; });  // inbox: optional, never blanks the page
  if (!s) return;
  S.setup = s; S.queue = q; S.lectures = l; S.folders = f; S.sem = sem; S.inbox = inbox;
  markSideLoaded();
  drawSidebar();
  if (!$("#jobs-wrap")) return;
  drawJobs();
  drawLibrary();
}
window.addEventListener("lt:folders", () => { if ($("#lib-wrap")) { $("#lib-wrap")._html = null; drawLibrary(); } });

// --- in progress (only shown when something is) --------------------------------------------------------------

function drawJobs() {
  const items = S.queue.items.filter((i) => i.status !== "done").reverse();
  const waiting = S.inbox?.waiting || [];  // watch folder: recordings that can't be queued yet
  const wrap = $("#jobs-wrap");
  if (!paint(wrap, items.length || waiting.length ? `<h2 class="group-title" id="prog">${t("progress")}</h2>
    <div class="card flat">${items.map(jobHtml).join("")}${waiting.map(inboxHtml).join("")}</div>` : "")) return;
  $$("[data-qa]", wrap).forEach((b) => b.addEventListener("click", async () => {
    try { await post(`/api/queue/${b.dataset.id}/${b.dataset.qa}`); } catch (e) { toast(e.message, true); }
    refreshDashboard();
  }));
}
function jobHtml(i) {
  const job = i.job ? i.job.split("/").pop() : null;
  const canRetry = ["failed", "notes_pending"].includes(i.status);
  const canRemove = !["transcribing", "notes"].includes(i.status);
  return `<div class="prog-row">
    <div class="prog-top">
      <span class="dot" data-course="${courseKey(i.course)}"></span><div class="prog-what"><div class="prog-title">${esc(i.display_title)}</div>
        <div class="prog-sub">${esc(courseName(i.course))}</div></div>
      <div class="prog-actions">
        ${job && i.status !== "queued" ? `<a class="btn btn-small" href="#/lecture/${encodeURIComponent(job)}">${t("open")}</a>` : ""}
        ${canRetry ? `<button class="btn btn-small" data-qa="retry" data-id="${i.id}">${t("retry")}</button>` : ""}
        ${canRemove ? `<button class="btn btn-small btn-plain" data-qa="remove" data-id="${i.id}">${t("remove")}</button>` : ""}
      </div>
    </div>
    <div class="prog-state"><span>${esc(statusText(i))}</span>${i.step_model ? `<span class="muted">${esc(i.step_model)}</span>` : ""}</div>
    ${progressHtml(i)}
    ${i.status === "notes_pending" && i.message ? `<div class="muted small">${esc(i.message.slice(0, 160))}</div>` : ""}
    ${i.status === "failed" && i.error ? `<div class="job-error">${esc(i.error)}</div>` : ""}
  </div>`;
}
function inboxHtml(w) {
  return `<div class="prog-row">
    <div class="prog-top">
      <span class="dot" data-course="${courseKey(w.course)}"></span><div class="prog-what"><div class="prog-title">${esc(w.title)}</div>
        <div class="prog-sub">${esc(courseName(w.course))} · ${t("inbox_label")}</div></div>
      <div class="prog-actions"><a class="btn btn-small" href="#/add">${t("inbox_add")}</a></div>
    </div>
    <div class="prog-state"><span>${t("inbox_waiting")}</span><span class="muted">${esc(w.why)}</span></div>
  </div>`;
}
