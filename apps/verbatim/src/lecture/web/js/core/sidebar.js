// Sidebar: library / in progress / settings, courses and own folders (with counts; folders are drop targets
// for lecture rows), and the status of speech-to-text, notes and the worker at the bottom.
import { api, post } from "./api.js";
import { $, $$ } from "./dom.js";
import { esc, fmtSem } from "./format.js";
import { S, isArchived } from "./state.js";
import { inlineEdit, paint, toast } from "./ui.js";

let loaded = false;

// Pages other than the library don't poll: fetch what the sidebar needs once.
export async function ensureSideData() {
  if (loaded) return drawSidebar();
  const [s, q, l, f, sem] = await Promise.all([api("/api/setup"), api("/api/queue"), api("/api/lectures"),
    api("/api/folders"), api("/api/semesters")]).catch(() => []);
  if (s) { S.setup = s; S.queue = q; S.lectures = l; S.folders = f; S.sem = sem; loaded = true; }
  drawSidebar();
}
export const markSideLoaded = () => { loaded = true; };

export function drawSidebar() {
  const [, page, arg] = location.hash.split("/");
  const sel = page === "c" || page === "f" ? `${page}:${decodeURIComponent(arg || "")}` : "";
  const done = S.lectures.filter((l) => l.id);
  const busy = S.queue.items.filter((i) => i.status !== "done").length;
  const link = (href, label, n, on, extra = "") =>
    `<a class="side-link ${on ? "on" : ""}" href="${href}" ${extra} ${on ? 'aria-current="page"' : ""}>${esc(label)}${n != null ? `<span class="n">${n}</span>` : ""}</a>`;
  const home = !page || page === "progress";
  const counts = (pred) => done.filter(pred).length;
  const current = S.courses.filter((c) => !isArchived(c.id));
  const pastSems = S.sem ? S.sem.semesters.filter((x) => x.archived).length : 0;
  const nav = `
    <div class="side-group">
      ${link("#/", t("nav_library"), done.length, home && !sel && page !== "progress")}
      ${busy ? link("#/progress", t("nav_progress"), busy, page === "progress") : ""}
      ${link("#/setup", t("nav_settings"), null, page === "setup")}
    </div>
    ${current.length ? `<div class="side-group"><div class="side-label">${S.sem && current.every((c) => S.sem.courses[c.id]?.semester === S.sem.current)
      ? esc(fmtSem(S.sem.current)) : t("nav_courses")}</div>
      ${current.map((c) => link(`#/c/${encodeURIComponent(c.id)}`, c.name, counts((l) => l.course === c.id), sel === `c:${c.id}`)).join("")}</div>` : ""}
    <div class="side-group">${link("#/archive", t("nav_archive"), pastSems ? (pastSems === 1 ? t("arch_n_1") : t("arch_n", { n: pastSems })) : null,
      page === "archive" || (sel.startsWith("c:") && isArchived(sel.slice(2))))}</div>
    <div class="side-group"><div class="side-label">${t("nav_folders")}</div>
      ${S.folders.folders.map((f) => link(`#/f/${encodeURIComponent(f.id)}`, f.name, counts((l) => S.folders.assign[l.id] === f.id),
        sel === `f:${f.id}`, `data-drop="${esc(f.id)}"`)).join("")}
      <button type="button" class="side-link side-new" id="side-new-folder">+ ${t("new_folder")}</button></div>`;
  if (paint($("#side-nav"), nav)) bindNav();
  drawStatus();
}

function bindNav() {
  $("#side-new-folder").addEventListener("click", (e) => {
    inlineEdit(e.currentTarget, "", async (name) => {
      const id = "f" + Date.now().toString(36);
      S.folders = await post("/api/folders", { ...S.folders, folders: [...S.folders.folders, { id, name }] });
    }, t("new_folder"), () => { $("#side-nav")._html = null; drawSidebar(); });
  });
  $$("[data-drop]", $("#side-nav")).forEach((f) => {
    f.addEventListener("dragover", (e) => { e.preventDefault(); f.classList.add("drop-target"); });
    f.addEventListener("dragleave", () => f.classList.remove("drop-target"));
    f.addEventListener("drop", async (e) => {
      e.preventDefault();
      f.classList.remove("drop-target");
      const id = e.dataTransfer.getData("text/lecture");
      if (!id) return;
      try { S.folders = await post("/api/folders", { ...S.folders, assign: { ...S.folders.assign, [id]: f.dataset.drop } }); }
      catch (err) { toast(err.message, true); }
      $("#side-nav")._html = null;
      drawSidebar();
      window.dispatchEvent(new Event("lt:folders"));  // the library list shows folder names
    });
  });
}

function drawStatus() {
  const s = S.setup;
  if (!s) return;
  const sttOk = s.stt.active_ok, fallback = s.stt.fallback;  // fallback: the first choice doesn't answer
  const html = `
    <a href="#/setup" title="${esc(t("side_stt"))}"><span class="dot ${!sttOk ? "bad" : fallback ? "wait" : ""}"></span>${esc(s.stt.active)}</a>
    <a href="#/setup" title="${esc(t("side_notes"))}"><span class="dot ${s.notes_paused ? "wait" : s.notes.ok ? "" : "bad"}"></span>${esc(s.notes.label)}${s.notes_paused ? ` · ${t("notes_paused")}` : ""}</a>
    ${s.termfix?.enabled ? `<a href="#/setup" title="${esc(t("side_suggest"))}${s.termfix.ok ? "" : ": " + esc(s.termfix.detail)}"><span class="dot ${s.termfix.ok ? "" : "bad"}"></span>${esc(s.termfix.model)}</a>` : ""}
    ${s.worker ? "" : `<a href="#/setup"><span class="dot bad"></span>${t("worker_off")}</a>`}`;
  paint($("#side-status"), html);
}
