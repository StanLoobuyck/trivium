// Sidebar: library / in progress / settings, courses and own folders (with counts; folders are drop targets
// for lecture rows), and the status of speech-to-text, notes and the worker at the bottom.
import { icon } from "/static/design/icons.js";
import { api, post } from "./api.js";
import { $, $$ } from "./dom.js";
import { esc, fmtSem } from "./format.js";
import { S, courseKey, isArchived, sortedCourses } from "./state.js";
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

const tag = (n) => (n != null && n !== 0 ? `<span class="count">${n}</span>` : "");
const rowLink = (href, label, n, on, lead, attrs = "") =>
  `<li><a class="row" href="${href}" ${attrs} ${on ? 'aria-current="page"' : ""}>${lead}<span class="row-main"><span>${esc(label)}</span></span>${tag(n)}</a></li>`;

// The parts that need no data from the server: same rows and same tab bar as Inhaal.
export function drawChrome() {
  const [, page] = location.hash.split("/");
  const setup = page === "setup";
  $("#side-add").innerHTML = `${icon("plus")}${esc(t("nav_add"))}`;
  $("#side-settings").innerHTML = rowLink("#/setup", t("nav_settings"), null, setup, icon("settings"));
  $("#lecture-back").innerHTML = `<span class="flip-icon">${icon("chevron")}</span>`;
  $("#lecture-back").setAttribute("aria-label", t("back_library"));
  const bar = $("#tabbar");
  bar.dataset.active = setup ? "1" : "0";
  bar.innerHTML = [["#/", "book", "nav_library", !setup], ["#/setup", "settings", "nav_settings", setup]].map(([href, name, key, on]) =>
    `<a class="tab" href="${href}" ${on ? 'aria-current="page"' : ""}>${icon(name)}<span>${esc(t(key))}</span></a>`).join("");
  const fab = $("#fab");
  fab.href = "#/add";
  fab.innerHTML = icon("plus");
  fab.setAttribute("aria-label", t("nav_add"));
  fab.hidden = setup || page === "add" || page === "lecture";
}

export function drawSidebar() {
  const [, page, arg] = location.hash.split("/");
  const sel = page === "c" || page === "f" ? `${page}:${decodeURIComponent(arg || "")}` : "";
  const done = S.lectures.filter((l) => l.id);
  const busy = S.queue.items.filter((i) => i.status !== "done").length;
  const home = !page || page === "lecture";
  const counts = (pred) => done.filter(pred).length;
  const current = sortedCourses().filter((c) => !isArchived(c.id));
  const pastSems = S.sem ? S.sem.semesters.filter((x) => x.archived).length : 0;
  const courseTitle = S.sem && current.every((c) => S.sem.courses[c.id]?.semester === S.sem.current) ? fmtSem(S.sem.current) : t("nav_courses");
  const nav = `
    <ul class="list list-side">
      ${rowLink("#/", t("nav_library"), done.length, home, icon("book"))}
      ${busy ? rowLink("#/progress", t("nav_progress"), busy, page === "progress", icon("overview")) : ""}
    </ul>
    ${current.length ? `<p class="group-title side-title">${esc(courseTitle)}</p>
    <ul class="list list-side">${current.map((c) => rowLink(`#/c/${encodeURIComponent(c.id)}`, c.name, counts((l) => l.course === c.id), sel === `c:${c.id}`,
      '<span class="dot"></span>', `data-course="${courseKey(c.id)}"`)).join("")}</ul>` : ""}
    <p class="group-title side-title">${t("nav_folders")}</p>
    <ul class="list list-side">
      ${S.folders.folders.map((f) => rowLink(`#/f/${encodeURIComponent(f.id)}`, f.name, counts((l) => S.folders.assign[l.id] === f.id),
        sel === `f:${f.id}`, icon("folder"), `data-drop="${esc(f.id)}"`)).join("")}
      <li><button type="button" class="row" id="side-new-folder">${icon("plus")}<span class="row-main"><span>${t("new_folder")}</span></span></button></li>
      ${rowLink("#/archive", t("nav_archive"), pastSems || null, page === "archive" || (sel.startsWith("c:") && isArchived(sel.slice(2))), icon("archive"))}
    </ul>`;
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
  const row = (label, state, tone, title = label) =>
    `<a class="model-row" href="#/setup" title="${esc(title)}"><span>${esc(label)}</span><span class="model-state"><span class="status-dot ${tone}"></span><span>${esc(state)}</span></span></a>`;
  const html = `${row(t("side_stt"), s.stt.active, !sttOk ? "bad" : fallback ? "wait" : "")}
    ${row(t("side_notes"), s.notes.label, s.notes_paused ? "wait" : s.notes.ok ? "" : "bad")}
    ${s.termfix?.enabled ? row(t("side_terms"), t(s.termfix.ok ? "side_ready" : "side_unreachable"), s.termfix.ok ? "" : "bad", s.termfix.ok ? t("side_suggest") : s.termfix.detail) : ""}
    ${s.worker ? "" : row(t("side_worker"), t("worker_off"), "bad")}`;
  paint($("#side-status"), html);
}
