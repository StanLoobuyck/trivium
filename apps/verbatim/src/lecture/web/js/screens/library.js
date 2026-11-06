// The lecture list on the home page: header (Library / a course / a folder + totals, search, sort), rows with
// date, length and notes status; row menu (rename, move to folder, delete); rows drag onto sidebar folders.
// Per course a block, lessons by number, parts of one lesson under one row that opens (order from library.py).
import { icon } from "/static/design/icons.js";
import { api, post } from "../core/api.js";
import { $, $$ } from "../core/dom.js";
import { esc, fmtDayShort, fmtDuration } from "../core/format.js";
import { ICON } from "../core/icons.js";
import { S, courseKey, courseName, isArchived, sortedCourses } from "../core/state.js";
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
    <span class="sub">${t(list.length === 1 ? "lib_hero_1" : "lib_hero", { dur: fmtDuration(total) })}</span>
    <div class="progress" role="img" aria-label="${t("lib_with_notes", { n: ready })}"><span style="--value: ${list.length ? ready / list.length : 0}"></span></div>
  </div>`);
  paint($("#lib-chips"), S.courses.length ? `<a class="chip" href="#/" ${libSel ? "" : 'aria-current="page"'}>${t("nav_library")}</a>
    ${sortedCourses().filter((c) => !isArchived(c.id)).map((c) => `<a class="chip" href="#/c/${encodeURIComponent(c.id)}" ${libSel === `c:${c.id}` ? 'aria-current="page"' : ""}>${esc(c.name)}</a>`).join("")}` : "");
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

// Lessons in parts: one row that opens; which ones are open is remembered in this browser.
const OPEN_KEY = "lt-open-groups";
const openGroups = new Set((() => { try { return JSON.parse(localStorage.getItem(OPEN_KEY)) || []; } catch { return []; } })());
const saveOpen = () => { try { localStorage.setItem(OPEN_KEY, JSON.stringify([...openGroups])); } catch { /* private window */ } };
const PART_RX = /\s*\b(?:deel|part)\s*\d+.*$/i;

// The order: per course a block (on "All" and in a folder), in it the lessons by number (the server's rank);
// newest = highest lesson first. Title = alphabetical. Blocks: the course with the newest lecture first.
function arrangeRows(list) {
  const cmp = libSort === "title" ? (a, b) => a.title.localeCompare(b.title, undefined, { numeric: true })
    : libSort === "old" ? (a, b) => a.rank - b.rank : (a, b) => b.rank - a.rank;
  const blocks = new Map();
  for (const l of list) (blocks.get(l.course) || blocks.set(l.course, []).get(l.course)).push(l);
  const newest = (ls) => ls.reduce((m, l) => ((l.date || "") > m ? l.date || "" : m), "");
  const oldest = (ls) => ls.reduce((m, l) => ((l.date || "~") < m ? l.date || "~" : m), "~");
  return [...blocks.entries()].map(([course, ls]) => ({ course, name: ls[0].course_name, items: groupParts(ls.sort(cmp)) }))
    .sort(libSort === "title" ? (a, b) => (a.name || "").localeCompare(b.name || "")
      : libSort === "old" ? (a, b) => oldest(a.items.flatMap(itemLectures)).localeCompare(oldest(b.items.flatMap(itemLectures)))
        : (a, b) => newest(b.items.flatMap(itemLectures)).localeCompare(newest(a.items.flatMap(itemLectures))));
}
const itemLectures = (it) => (it.parts || [it]);
// Two or more parts of the same lesson become one item at the place of the first; parts always 1, 2, 3 …
function groupParts(sorted) {
  const count = new Map();
  for (const l of sorted) if (l.group) count.set(l.group, (count.get(l.group) || 0) + 1);
  const out = [], seen = new Map();
  for (const l of sorted) {
    if (!l.group || count.get(l.group) < 2) { out.push(l); continue; }
    if (!seen.has(l.group)) { const g = { key: l.group, title: l.title.replace(PART_RX, ""), parts: [] }; seen.set(l.group, g); out.push(g); }
    seen.get(l.group).parts.push(l);
  }
  for (const g of seen.values()) g.parts.sort((a, b) => (a.part || 0) - (b.part || 0));
  return out;
}

function groupNotes(parts) {
  const busy = parts.find((l) => !l.has_notes && l.queue && l.status !== "done");
  if (busy) return notesText(busy);
  const ready = parts.filter((l) => l.has_notes).length;
  return ready === parts.length ? t("notes_ready") : ready ? t("group_notes", { n: ready, total: parts.length }) : t("notes_none");
}

function subLine(l, showCourse) {
  const folder = S.folders.folders.find((f) => f.id === S.folders.assign[l.id]);
  return [showCourse ? l.course_name : "", folder && !libSel.startsWith("f:") ? folder.name : "",
    isArchived(l.course) ? t("archived") : ""].filter(Boolean).join(" · ");
}

function lectureRow(l, { part = false, showCourse } = {}) {
  const sub = part ? "" : subLine(l, showCourse);
  const title = part ? (l.title.match(PART_RX)?.[0].trim() || l.title).replace(/^./, (c) => c.toUpperCase()) : l.title;
  return `<li class="lecture${part ? " lecture-part" : ""}" draggable="true" data-id="${esc(l.id)}"><div class="row" data-course="${courseKey(l.course)}">
      <span class="dot"></span>
      <span class="row-main"><a class="row-title" href="#/lecture/${encodeURIComponent(l.id)}">${esc(title)}</a>
        ${sub ? `<span class="sub">${esc(sub)}</span>` : ""}<span class="sub">${esc(notesText(l))}</span></span>
      <span class="row-trail">${esc(fmtDayShort(l.date))} · ${esc(fmtDuration(l.duration_s))}
        <button class="icon-btn" data-menu="${esc(l.id)}" aria-label="${t("rename")}, ${t("move_to")}, ${t("delete")}">${icon("more")}</button></span>
    </div></li>`;
}

function groupRow(g, showCourse) {
  const open = openGroups.has(g.key);
  const first = g.parts[0];
  const total = g.parts.reduce((a, l) => a + (l.duration_s || 0), 0);
  const sub = [t("group_parts", { n: g.parts.length }), subLine(first, showCourse)].filter(Boolean).join(" · ");
  const head = `<li class="lecture-group${open ? " is-open" : ""}" draggable="true" data-group="${esc(g.key)}"
      data-ids="${esc(g.parts.map((l) => l.id).join("\n"))}"><div class="row" data-course="${courseKey(first.course)}">
      <span class="dot"></span>
      <span class="row-main"><button class="row-title group-toggle" aria-expanded="${open}">${esc(g.title)}</button>
        <span class="sub">${esc(sub)}</span><span class="sub">${esc(groupNotes(g.parts))}</span></span>
      <span class="row-trail">${esc(fmtDayShort(first.date))} · ${esc(fmtDuration(total))}
        <span class="group-chevron">${icon("chevron")}</span></span>
    </div></li>`;
  return head + (open ? g.parts.map((l) => lectureRow(l, { part: true })).join("") : "");
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
  const shown = done.filter((l) => inSel(l) && (!q || `${l.title} ${l.course_name}`.toLowerCase().includes(q)));
  if (!shown.length) {
    paint(wrap, `<div class="empty-line">${libSel.startsWith("f:") ? t("folder_empty") : t("nothing_here")}</div>`);
    return;
  }
  const blocks = arrangeRows(shown);
  const heads = !libSel.startsWith("c:");  // one course: no heading needed
  const html = blocks.map((b) => `<section class="lib-block">
      ${heads ? `<h2 class="group-title lib-course" data-course="${courseKey(b.course)}"><span class="dot"></span>${esc(b.name || b.course)}</h2>` : ""}
      <ul class="list lectures">${b.items.map((it) => (it.parts ? groupRow(it, false) : lectureRow(it, { showCourse: !heads }))).join("")}</ul>
    </section>`).join("");
  if (!paint(wrap, html)) return;
  $$(".lecture", wrap).forEach((r) => {
    r.addEventListener("click", (e) => { if (!e.target.closest("button, a, input")) location.hash = `#/lecture/${encodeURIComponent(r.dataset.id)}`; });
    r.addEventListener("dragstart", (e) => { e.stopPropagation(); e.dataTransfer.setData("text/lecture", r.dataset.id); r.classList.add("dragging"); });
    r.addEventListener("dragend", () => r.classList.remove("dragging"));
  });
  $$(".lecture-group", wrap).forEach((r) => {
    const toggle = () => {
      if (openGroups.has(r.dataset.group)) openGroups.delete(r.dataset.group); else openGroups.add(r.dataset.group);
      saveOpen();
      drawRows();
      $(`.lecture-group[data-group="${CSS.escape(r.dataset.group)}"] .group-toggle`, wrap)?.focus();
    };
    r.addEventListener("click", (e) => { if (!e.target.closest("a, input") && !e.target.closest("[data-menu]")) toggle(); });
    r.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/lecture", r.dataset.ids); r.classList.add("dragging"); });
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
