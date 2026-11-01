// Archive (#/archive): semesters, archive / move back, video+audio copies to the Mac and back (with progress).
// Backend: /api/semesters, /api/courses/<id>/archived, /api/archive/* (src/lecture/api/archive.py).
import { api, post } from "../core/api.js";
import { $, $$, view } from "../core/dom.js";
import { esc, fmtDate, fmtHm, fmtSem, fmtSize } from "../core/format.js";
import { S } from "../core/state.js";
import { drawSidebar } from "../core/sidebar.js";
import { paint, poll, toast } from "../core/ui.js";
import { setCourseArchived } from "../shared/actions.js";

let moveMedia = true;

export async function renderArchive() {
  view.innerHTML = `<h1 class="large-title">${t("arch_title")}</h1>
    <p class="card sub">${t("arch_sub")}</p>
    <section id="arch-progress"></section><section id="arch-body"></section>
    <p class="muted small">${t("arch_originals")}</p>`;
  await refresh();
  poll(refresh, 3000);
}

async function refresh() {
  const [sem, prog] = await Promise.all([api("/api/semesters"), api("/api/archive/progress")]).catch((e) => { toast(e.message, true); return []; });
  if (!sem || !$("#arch-body")) return;
  S.sem = sem;
  drawSidebar();
  drawProgress(prog);
  drawBody(sem, prog.running);
}

function drawProgress(p) {
  let html = "";
  if (p.running) {
    const pct = p.total ? Math.round((p.done / p.total) * 100) : 0;
    html = `<div class="card flat arch-prog"><div>${esc(t(p.action === "move" ? "arch_moving" : "arch_restoring", { done: p.done, total: p.total, label: p.label }))}</div>
      <div class="prog-bar"><span style="width:${pct}%"></span></div></div>`;
  } else if (p.error) {
    html = `<div class="job-error">${esc(t("arch_error", { error: p.error }))}</div>`;
  } else if (p.finished) {
    html = `<div class="card flat arch-prog">${esc(p.action === "move" ? t("arch_done", { size: fmtSize(p.bytes || 0) }) : t("arch_restored"))}</div>`;
  }
  paint($("#arch-progress"), html);
}

function mediaLine(lectures) {
  const local = lectures.reduce((a, l) => a + l.local_bytes, 0);
  const onMac = lectures.some((l) => l.on_mac);
  if (onMac && !local) return `<span class="status-dot off"></span>${t("arch_media_mac")}`;
  if (local) return `<span class="status-dot"></span>${t("arch_media_local", { size: fmtSize(local) })}`;
  return `<span class="status-dot off"></span>${t("arch_media_none")}`;
}

function courseHtml(c, busy) {
  const total = c.lectures.reduce((a, l) => a + (l.duration_s || 0), 0);
  const local = c.lectures.some((l) => l.local_bytes), onMac = c.lectures.some((l) => l.on_mac);
  return `<div class="arch-course ${c.archived ? "" : "active"}">
    <div class="arch-course-head">
      <div><a href="#/c/${encodeURIComponent(c.id)}" class="row-title">${esc(c.name)}</a>
        <div class="row-sub">${t(c.lectures.length === 1 ? "lectures_1" : "lectures_n", { n: c.lectures.length })}${total ? ` · ${fmtHm(total)}` : ""}
          · ${c.archived ? t("archived") : t("arch_in_list")}</div></div>
      <div class="arch-media muted small">${mediaLine(c.lectures)}</div>
      <div class="arch-actions">
        <button class="btn btn-small" data-arch="${esc(c.id)}" data-to="${c.archived ? "0" : "1"}" ${busy ? "disabled" : ""}>${c.archived ? t("arch_course_back") : t("arch_course")}</button>
        ${local ? `<button class="btn btn-small" data-move="${esc(c.id)}" ${busy ? "disabled" : ""}>${t("arch_move_media")}</button>` : ""}
        ${onMac ? `<button class="btn btn-small" data-restore="${esc(c.id)}" ${busy ? "disabled" : ""}>${t("arch_restore")}</button>` : ""}
      </div>
    </div>
    ${c.lectures.length ? `<ul class="arch-lectures">${c.lectures.sort((a, b) => (b.date || "").localeCompare(a.date || "")).map((l) => `
      <li><a href="#/lecture/${encodeURIComponent(l.id)}">${esc(l.title)}</a>
        <span class="muted small">${esc(fmtDate(l.date))}${l.duration_s ? ` · <span class="mono">${fmtHm(l.duration_s)}</span>` : ""}</span></li>`).join("")}</ul>` : ""}
  </div>`;
}

// Every semester with courses, newest first: per course its state and Archive / Move back, media buttons;
// per semester "Archive semester" (+ media to the Mac) and "Move back to current".
function drawBody(sem, busy) {
  const sems = sem.semesters.filter((s) => s.courses.length);
  const html = sems.length ? sems.map((s) => {
    const active = s.courses.filter((c) => !c.archived), archived = s.courses.filter((c) => c.archived);
    return `<section class="arch-sem">
      <div class="arch-sem-head">
        <h2>${esc(fmtSem(s.name))}${s.current ? ` <span class="muted" style="font-weight:400">· ${t("arch_current")}</span>` : ""}</h2>
        <div class="arch-actions">
          ${active.length ? `<label class="arch-cb"><input type="checkbox" data-media-cb ${moveMedia ? "checked" : ""}> ${t("arch_move_media_cb")}</label>
            <button class="btn btn-small" data-arch-sem="${esc(s.name)}" ${busy ? "disabled" : ""}>${t("arch_sem")}</button>` : ""}
          ${archived.length ? `<button class="btn btn-small btn-plain" data-back="${esc(s.name)}" ${busy ? "disabled" : ""}>${t("arch_back")}</button>` : ""}
        </div>
      </div>
      <div class="card flat">${s.courses.map((c) => courseHtml(c, busy)).join("")}</div>
    </section>`;
  }).join("") : `<div class="empty-line">${t("arch_empty")}</div>`;
  if (!paint($("#arch-body"), html)) return;
  const all = sem.semesters.flatMap((s) => s.courses);
  const jobsOf = (id) => all.find((c) => c.id === id).lectures.map((l) => l.id);
  const act = async (fn) => { try { await fn(); } catch (e) { toast(e.message, true); } refresh(); };
  $$("[data-media-cb]").forEach((cb) => cb.addEventListener("change", (e) => {
    moveMedia = e.target.checked;
    $$("[data-media-cb]").forEach((x) => { x.checked = moveMedia; });
  }));
  $$("[data-arch]").forEach((b) => b.addEventListener("click", () => act(() => setCourseArchived(b.dataset.arch, b.dataset.to === "1"))));
  $$("[data-arch-sem]").forEach((b) => b.addEventListener("click", () => act(async () => {
    const s = sem.semesters.find((x) => x.name === b.dataset.archSem);
    const active = s.courses.filter((c) => !c.archived);
    for (const c of active) await setCourseArchived(c.id, true);
    if (moveMedia) await post("/api/archive/move", { jobs: active.flatMap((c) => c.lectures.map((l) => l.id)) });
  })));
  $$("[data-back]").forEach((b) => b.addEventListener("click", () => act(async () => {
    const s = sem.semesters.find((x) => x.name === b.dataset.back);
    for (const c of s.courses.filter((x) => x.archived)) await setCourseArchived(c.id, false);
  })));
  $$("[data-move]").forEach((b) => b.addEventListener("click", () => act(() => post("/api/archive/move", { jobs: jobsOf(b.dataset.move) }))));
  $$("[data-restore]").forEach((b) => b.addEventListener("click", () => act(() => post("/api/archive/restore", { jobs: jobsOf(b.dataset.restore) }))));
}
