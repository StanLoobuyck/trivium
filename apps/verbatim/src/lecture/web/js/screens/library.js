// The lecture list on the home page: header (Library / a course / a folder + totals, search, sort), rows with
// date, length and notes status; row menu (rename, move to folder, delete); rows drag onto sidebar folders.
import { icon } from "/static/design/icons.js";
import { api, post } from "../core/api.js";
import { $, $$ } from "../core/dom.js";
import { esc, fmtDate, fmtHm, fmtLong } from "../core/format.js";
import { ICON } from "../core/icons.js";
import { S, courseKey, courseName, isArchived } from "../core/state.js";
import { drawSidebar } from "../core/sidebar.js";
import { closeMenus, inlineEdit, paint, toast } from "../core/ui.js";
import { deleteLecture, renameLecture, setCourseArchived } from "../shared/actions.js";
import { statusText } from "../shared/jobstatus.js";
import { refreshDashboard } from "./dashboard.js";

let libSel = "", libSort = "new", libQ = "";

export function setLibrarySel(sel) {
  if (sel !== libSel) libQ = "";
  libSel = sel;
}

const selName = () => {
  if (!libSel) return t("nav_library");
  const [kind, id] = [libSel.slice(0, 1), libSel.slice(2)];
  return kind === "c" ? courseName(id) : (S.folders.folders.find((f) => f.id === id) || {}).name;
};
function inSel(l) {
  if (libSel.startsWith("c:")) return l.course === libSel.slice(2);
  if (libSel.startsWith("f:")) return S.folders.assign[l.id] === libSel.slice(2);
  return true;
}

export function drawLibrary() {
  if (S.editing || !$("#lib-wrap")) return;  // don't rebuild under an open rename field
  drawHead();
  drawRows();
}

function drawHead() {
  const name = selName();
  if (!name) { location.hash = "#/"; return; }  // folder was deleted
  const list = S.lectures.filter((l) => l.id && inSel(l));
  const total = list.reduce((a, l) => a + (l.duration_s || 0), 0);
  const ready = list.filter((l) => l.has_notes).length;
  const kind = libSel.slice(0, 1);
  $("#lib-title").textContent = name;
  paint($("#lib-hero"), `<div class="hero">
    <span class="hero-number">${list.length}</span>
    <span class="sub">${t(list.length === 1 ? "lib_hero_1" : "lib_hero", { dur: fmtLong(total) })}</span>
    <div class="progress" role="img" aria-label="${t("lib_with_notes", { n: ready })}"><span style="--value: ${list.length ? ready / list.length : 0}"></span></div>
  </div>`);
  paint($("#lib-chips"), S.courses.length ? `<a class="chip" href="#/" ${libSel ? "" : 'aria-current="page"'}>${t("nav_library")}</a>
    ${S.courses.filter((c) => !isArchived(c.id)).map((c) => `<a class="chip" href="#/c/${encodeURIComponent(c.id)}" ${libSel === `c:${c.id}` ? 'aria-current="page"' : ""}>${esc(c.name)}</a>`).join("")}` : "");
  drawTools();
  const action = (id, label, extra = "") => `<li><button class="row ${extra}" id="${id}"><span class="row-main"><span>${label}</span></span></button></li>`;
  if (paint($("#lib-actions"), libSel ? `<ul class="list">
      ${action("rename-sel", t("rename"))}
      ${kind === "c" ? action("archive-sel", isArchived(libSel.slice(2)) ? t("arch_course_back") : t("arch_course")) : ""}
      ${kind === "f" ? action("del-folder", t("delete_folder"), "row-danger") : ""}
    </ul>` : "")) bindActions(kind);
}

function drawTools() {
  const box = $("#lib-tools");
  if (box.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;  // typing in the search box
  if (!paint(box, `<div class="segmented" role="group" aria-label="${t("sort_label")}">
      ${["new", "old", "title"].map((v) => `<button aria-pressed="${libSort === v}" data-sort="${v}">${t("sort_short_" + v)}</button>`).join("")}
    </div>
    <label class="sr-only" for="lib-q">${t("search")}</label>
    <input class="field" type="search" id="lib-q" placeholder="${t("search")}" value="${esc(libQ)}">`)) return;
  $("#lib-q").addEventListener("input", (e) => { libQ = e.target.value; drawRows(); });
  $$("[data-sort]", box).forEach((b) => b.addEventListener("click", () => { libSort = b.dataset.sort; drawTools(); drawRows(); }));
}

function bindActions(kind) {
  const redraw = () => { $("#lib-actions")._html = null; $("#side-nav")._html = null; refreshDashboard(); };
  $("#rename-sel")?.addEventListener("click", () => {
    const id = libSel.slice(2);
    inlineEdit($("#lib-title"), $("#lib-title").textContent, kind === "c"
      ? async (name) => { await post("/api/courses", { ...S.courses.find((c) => c.id === id), name }); S.courses = await api("/api/courses"); }
      : async (name) => { await saveFolders({ ...S.folders, folders: S.folders.folders.map((f) => (f.id === id ? { ...f, name } : f)) }); },
    "", redraw);
  });
  $("#archive-sel")?.addEventListener("click", async () => {
    const id = libSel.slice(2);
    try { await setCourseArchived(id, !isArchived(id)); } catch (e) { toast(e.message, true); }
    redraw();
  });
  $("#del-folder")?.addEventListener("click", async () => {
    const id = libSel.slice(2);
    const assign = Object.fromEntries(Object.entries(S.folders.assign).filter(([, f]) => f !== id));
    await saveFolders({ folders: S.folders.folders.filter((f) => f.id !== id), assign });
    location.hash = "#/";
  });
}

function notesText(l) {
  if (l.has_notes) return t("notes_ready");
  if (l.queue && l.status !== "done") return statusText({ ...l.queue, status: l.status });
  return t("notes_none");
}

function drawRows() {
  const wrap = $("#lib-wrap");
  const done = S.lectures.filter((l) => l.id);
  if (!done.length) {
    paint(wrap, `<div class="empty">${ICON.inbox}<h2>${t("no_lectures")}</h2><p>${t("no_lectures_hint")}</p>
      <a class="btn btn-primary" href="#/add" style="margin-top:12px">${t("nav_add")}</a></div>`);
    return;
  }
  const q = libQ.trim().toLowerCase();
  let shown = done.filter((l) => inSel(l) && (!q || `${l.title} ${l.course_name}`.toLowerCase().includes(q)));
  shown = shown.sort(libSort === "title" ? (a, b) => a.title.localeCompare(b.title, undefined, { numeric: true })
    : libSort === "old" ? (a, b) => (a.date || "").localeCompare(b.date || "") : (a, b) => (b.date || "").localeCompare(a.date || ""));
  if (!shown.length) {
    paint(wrap, `<div class="empty-line">${libSel.startsWith("f:") ? t("folder_empty") : t("nothing_here")}</div>`);
    return;
  }
  const rows = shown.map((l) => {
    const data = `data-course="${courseKey(l.course)}"`;
    const folder = S.folders.folders.find((f) => f.id === S.folders.assign[l.id]);
    const sub = [libSel.startsWith("c:") ? "" : l.course_name, folder && !libSel.startsWith("f:") ? folder.name : "",
      isArchived(l.course) ? t("archived") : ""].filter(Boolean).join(" · ");
    return `<li class="lecture" draggable="true" data-id="${esc(l.id)}"><div class="row" ${data}>
      <span class="dot"></span>
      <span class="row-main"><a class="row-title" href="#/lecture/${encodeURIComponent(l.id)}">${esc(l.title)}</a>
        ${sub ? `<span class="sub">${esc(sub)}</span>` : ""}<span class="sub">${esc(notesText(l))}</span></span>
      <span class="row-trail">${esc(fmtDate(l.date))} · ${esc(fmtHm(l.duration_s))}
        <button class="icon-btn" data-menu="${esc(l.id)}" aria-label="${t("rename")}, ${t("move_to")}, ${t("delete")}">${icon("more")}</button></span>
    </div></li>`;
  }).join("");
  if (!paint(wrap, `<ul class="list lectures">${rows}</ul>`)) return;
  $$(".lecture", wrap).forEach((r) => {
    r.addEventListener("click", (e) => { if (!e.target.closest("button, a, input")) location.hash = `#/lecture/${encodeURIComponent(r.dataset.id)}`; });
    r.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/lecture", r.dataset.id); r.classList.add("dragging"); });
    r.addEventListener("dragend", () => r.classList.remove("dragging"));
  });
  $$("[data-menu]", wrap).forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); openRowMenu(b); }));
}

async function saveFolders(data) {
  try { S.folders = await post("/api/folders", data); } catch (e) { toast(e.message, true); }
}
async function moveTo(lectureId, folderId) {
  const assign = { ...S.folders.assign };
  if (folderId) assign[lectureId] = folderId; else delete assign[lectureId];
  await saveFolders({ ...S.folders, assign });
  $("#lib-wrap")._html = null;
  $("#side-nav")._html = null;
  drawSidebar();
  drawLibrary();
}

function openRowMenu(btn) {
  closeMenus();
  const id = btn.dataset.menu;
  const m = document.createElement("div");
  m.className = "menu";
  m.innerHTML = `<button data-rename>${t("rename")}</button><hr>` +
    `<div class="block-title" style="padding:6px 10px">${t("move_to")}</div>` +
    (S.folders.folders.length ? S.folders.folders.map((f) => `<button data-to="${esc(f.id)}">${S.folders.assign[id] === f.id ? "✓ " : ""}${esc(f.name)}</button>`).join("")
      : `<p class="muted small" style="padding:4px 10px 8px">${t("no_folders_yet")}</p>`) +
    (S.folders.assign[id] ? `<hr><button data-to="">${t("remove_from_folder")}</button>` : "") +
    `<hr><button class="danger" data-delete>${t("delete_lecture")}</button>`;
  // a pop-up on top of the page (not inside the table, which would grow and scroll); opens upwards near the bottom
  m.classList.add("pop");
  document.body.append(m);
  const r = btn.getBoundingClientRect();
  const below = window.innerHeight - r.bottom;
  m.style.left = `${Math.max(8, r.right - m.offsetWidth)}px`;
  m.style.top = below > m.offsetHeight + 12 ? `${r.bottom + 4}px` : `${Math.max(8, r.top - m.offsetHeight - 4)}px`;
  $$("[data-to]", m).forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); closeMenus(); moveTo(id, b.dataset.to); }));
  $("[data-rename]", m).addEventListener("click", (e) => {
    e.stopPropagation();
    closeMenus();
    const title = btn.closest(".lecture").querySelector(".row-title");
    inlineEdit(title, title.textContent, (name) => renameLecture(id, name), "", () => { $("#lib-wrap")._html = null; drawLibrary(); });
  });
  $("[data-delete]", m).addEventListener("click", async (e) => {
    e.stopPropagation();
    closeMenus();
    if (await deleteLecture(id)) refreshDashboard();
  });
}
