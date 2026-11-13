// Home = the library: all lectures (or one course / folder). Bezig = only what is running. Both polled every 3 s.
import { api, post } from "../core/api.js";
import { $, $$, view } from "../core/dom.js";
import { esc } from "../core/format.js";
import { S, courseKey, courseName } from "../core/state.js";
import { drawSidebar, markSideLoaded } from "../core/sidebar.js";
import { paint, poll, toast, toastAction } from "../core/ui.js";
import { progressHtml, statusText } from "../shared/jobstatus.js";
import { drawLibrary, setLibrarySel } from "./library.js";

// sel: "" (all), "c:<course>" or "f:<folder>"
export async function renderDashboard(sel = "") {
  setLibrarySel(sel);
  view.innerHTML = `
    <h1 class="large-title" id="lib-title"></h1>
    <nav class="chips narrow-only" id="lib-chips" aria-label="${t("nav_courses")}"></nav>
    <div class="overview">
      <div class="overview-side flow"><section id="lib-hero"></section><section id="lib-busy"></section></div>
      <div class="overview-main flow"><section id="lib-update"></section><section class="stack-tight" id="lib-tools"></section><section id="lib-wrap"></section></div>
      <div class="overview-extra flow" id="lib-actions"></div>
    </div>`;
  await refreshDashboard();
  poll(refreshDashboard, 3000);
}

export async function renderProgress() {
  view.innerHTML = `<h1 class="large-title">${t("nav_progress")}</h1><section class="progress-page" id="jobs-wrap"></section>`;
  await refreshDashboard();
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
  if ($("#jobs-wrap")) drawJobs();
  if ($("#lib-wrap")) { drawUpdate(); drawBusyLink(); drawLibrary(); }
}

// --- update (Windows app) -------------------------------------------------------------------------------------

let updating = false;

function drawUpdate() {
  const u = S.setup?.update;
  const html = updating ? `<div class="banner" role="status"><span>${esc(t("upd_restarting"))}</span></div>`
    : u ? `<div class="banner"><span>${esc(t("upd_ready", { version: u.version }))}</span>
        <span class="banner-actions"><button class="btn btn-small btn-primary" id="upd-now">${esc(t("upd_now"))}</button></span></div>` : "";
  if (!paint($("#lib-update"), html)) return;
  $("#upd-now")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      await post("/api/update");
    } catch (err) {
      e.target.disabled = false;
      toast(/busy/.test(err.message) ? t("upd_busy") : err.message, true);
      return;
    }
    updating = true;
    drawUpdate();
    waitForRestart();
  });
}

// The app quits, the installer puts the new version in place and starts it again: reload once it answers.
function waitForRestart() {
  let wentAway = false;
  const timer = setInterval(async () => {
    try {
      await fetch("/api/today", { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(); });
      if (wentAway) { clearInterval(timer); location.reload(); }
    } catch { wentAway = true; }
  }, 2000);
}
window.addEventListener("lt:folders", () => { if ($("#lib-wrap")) { $("#lib-wrap")._html = null; drawLibrary(); } });

// --- in progress --------------------------------------------------------------------------------------------

// Stop: the row goes at once; the request only goes out once the Undo toast is gone (5 s). Stays hidden until the
// worker has stopped it (it notices at its next step, within about a minute).
const stopping = new Set();
const RUNNING = ["transcribing", "notes", "latex"];
const activeJobs = () => S.queue.items.filter((i) => i.status !== "done" && !stopping.has(i.id)).reverse();
const waitingJobs = () => (S.inbox?.waiting || []).filter((w) => !stopping.has(w.media));  // watch folder
const combining = (w) => w.why.startsWith("combining");

function forgetStopped() {
  const present = new Set([...S.queue.items.map((i) => i.id), ...(S.inbox?.waiting || []).map((w) => w.media)]);
  for (const key of stopping) if (!present.has(key)) stopping.delete(key);
}

function stop(key, request) {
  stopping.add(key);
  drawJobs();
  drawBusyLink();
  toastAction(t("stopped_toast"), t("undo"), {
    onAction: () => { stopping.delete(key); drawJobs(); drawBusyLink(); },
    onTimeout: async () => {
      try { await request(); } catch (e) { stopping.delete(key); toast(e.message, true); }
      refreshDashboard();
    },
  });
}

// The tab bar has no Bezig, so the library always leads there.
function drawBusyLink() {
  if (!$("#lib-busy")) return;  // only on the library
  const n = activeJobs().length + waitingJobs().length;
  paint($("#lib-busy"), n ? `<a class="btn btn-block" href="#/progress">${t("nav_progress")} · ${n}</a>` : "");
}

function drawJobs() {
  if (!$("#jobs-wrap")) return;
  forgetStopped();
  const items = activeJobs();
  const waiting = waitingJobs();
  const wrap = $("#jobs-wrap");
  if (!paint(wrap, items.length || waiting.length ? `<div class="card flat">${items.map(jobHtml).join("")}${waiting.map(inboxHtml).join("")}</div>`
    : `<div class="empty"><p>${t("progress_empty")}</p></div>`)) return;
  $$("[data-qa]", wrap).forEach((b) => b.addEventListener("click", async () => {
    try {
      const r = await post(`/api/queue/${b.dataset.id}/${b.dataset.qa}`);
      // a recording from a course folder (Velox) starts over and waits for slides there
      if (r.waits_for_slides) toast(t("queue_removed_restart", { folder: r.waits_for_slides }), false, 10000);
    } catch (e) { toast(e.message, true); }
    refreshDashboard();
  }));
  $$("[data-stop]", wrap).forEach((b) => b.addEventListener("click", () =>
    stop(b.dataset.stop, () => post(`/api/queue/${b.dataset.stop}/stop`))));
  $$("[data-stop-media]", wrap).forEach((b) => b.addEventListener("click", () =>
    stop(b.dataset.stopMedia, () => post("/api/inbox/stop", { media: b.dataset.stopMedia }))));
  $$("[data-start-media]", wrap).forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    try { await post("/api/inbox/start", { media: b.dataset.startMedia }); toast(t("inbox_started")); }
    catch (e) { toast(e.message, true); b.disabled = false; }
    refreshDashboard();
  }));
}
function jobHtml(i) {
  const job = i.job ? i.job.split("/").pop() : null;
  const canRetry = ["failed", "notes_pending"].includes(i.status);
  const canRemove = !["transcribing", "notes", "latex"].includes(i.status);
  return `<div class="prog-row">
    <div class="prog-top">
      <span class="dot" data-course="${courseKey(i.course)}"></span><div class="prog-what"><div class="prog-title">${esc(i.display_title)}</div>
        <div class="prog-sub">${esc(courseName(i.course))}</div></div>
      <div class="prog-actions">
        ${job && i.status !== "queued" ? `<a class="btn btn-small" href="#/lecture/${encodeURIComponent(job)}">${t("open")}</a>` : ""}
        ${canRetry ? `<button class="btn btn-small" data-qa="retry" data-id="${i.id}">${t("retry")}</button>` : ""}
        ${canRemove ? `<button class="btn btn-small btn-plain" data-qa="remove" data-id="${i.id}">${t("remove")}</button>` : ""}
        ${RUNNING.includes(i.status) ? `<button class="btn btn-small btn-plain" data-stop="${i.id}">${t("stop")}</button>` : ""}
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
      <div class="prog-actions">${combining(w)
        ? `<button class="btn btn-small btn-plain" data-stop-media="${esc(w.media)}">${t("stop")}</button>`
        : `${w.slides_wait ? `<button class="btn btn-small" data-start-media="${esc(w.media)}">${t("inbox_start")}</button>` : ""}<a class="btn btn-small ${w.slides_wait ? "btn-plain" : ""}" href="#/add">${t("inbox_add")}</a>`}</div>
    </div>
    <div class="prog-state"><span>${t("inbox_waiting")}</span><span class="muted">${esc(w.why)}</span></div>
  </div>`;
}
