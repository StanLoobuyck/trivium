// Upload panel on the dashboard: drop / pick recordings + slides, fill in course/title/date/language, queue them.
import { api, post } from "../core/api.js";
import { $, $$ } from "../core/dom.js";
import { esc, fmtDate, fmtSize } from "../core/format.js";
import { ICON } from "../core/icons.js";
import { S, courseLang, sortedCourses } from "../core/state.js";
import { inlineEdit, toast } from "../core/ui.js";

let picked = [], pickedSlides = [], suggestions = null, notesPolicy = "never";
let lastCourse = (() => { try { return localStorage.getItem("lt-course") || ""; } catch { return ""; } })();
const VIDEO_RX = /\.(mp4|mkv|mov|webm|m4v|m4a|mp3|wav|flac|ogg|opus|aac)$/i;
const SLIDE_RX = /\.(pdf|pptx)$/i;

export async function drawUpload() {
  const box = $("#upload");
  if (!box) return;
  box.innerHTML = `
    <p class="sub">${t("add_sub")}</p>
    <div class="drop" id="drop">
      <span class="drop-icon">${ICON.upload}</span>
      <div>
        <b>${t("upload_drop")}</b> <span class="muted">${t("upload_or")}</span>
        <label class="link">${t("upload_browse")}<input type="file" id="file-input" multiple accept="video/*,audio/*,.pdf,.pptx" hidden></label>
        <p class="muted small">${t("upload_hint")}</p>
      </div>
    </div>
    <div class="recent" id="recent"></div>
    <div class="pending-add" id="pending" hidden></div>`;
  const drop = $("#drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); uploadFiles([...e.dataTransfer.files]); });
  $("#file-input").addEventListener("change", (e) => { uploadFiles([...e.target.files]); e.target.value = ""; });
  if (!suggestions) suggestions = await api("/api/suggestions").catch(() => ({ videos: [], slides: [] }));
  drawRecent();
  drawPending();
}

function drawRecent() {
  const box = $("#recent");
  if (!box) return;
  const pickedPaths = new Set(picked.map((p) => p.path));
  const vids = suggestions.videos;
  box.innerHTML = `<h4>${t("recent")}</h4>` + (vids.length
    ? `<div class="chips chips-wrap">${vids.map((v, i) => `<button type="button" class="chip" aria-pressed="${pickedPaths.has(v.path)}" data-vi="${i}" title="${esc(v.path)}">${pickedPaths.has(v.path) ? "✓ " : ""}${esc(v.title)} · ${esc(fmtDate(v.date))} · ${fmtSize(v.size)}</button>`).join("")}</div>`
    : `<p class="muted small">${t("recent_none")}</p>`);
  $$("[data-vi]", box).forEach((b) => b.addEventListener("click", () => {
    const v = vids[b.dataset.vi];
    if (picked.some((p) => p.path === v.path)) picked = picked.filter((p) => p.path !== v.path);
    else addPicked(v);
    drawRecent();
    drawPending();
  }));
}

function addPicked(v) {
  if (picked.some((p) => p.path === v.path)) return;
  const course = v.course || lastCourse || (S.courses[0] || {}).id || "";
  picked.push({ path: v.path, name: v.name, title: v.title, date: v.date, course, language: courseLang(course) });
}

async function uploadFiles(files) {
  const pending = $("#pending");
  for (const f of files) {
    if (!VIDEO_RX.test(f.name) && !SLIDE_RX.test(f.name)) { toast(`${f.name}: ?`, true); continue; }
    const note = document.createElement("div");
    note.className = "uploading";
    note.textContent = t("uploading", { name: f.name });
    $("#upload").append(note);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await api("/api/upload", { method: "POST", body: fd });
      if (SLIDE_RX.test(f.name)) pickedSlides.push(r.path); else addPicked(r);
    } catch (e) { toast(`${f.name}: ${e.message}`, true); }
    note.remove();
  }
  if (pending) drawPending();
}

function drawPending() {
  const box = $("#pending");
  if (!box) return;
  box.hidden = !picked.length;
  if (!picked.length) { box.innerHTML = ""; return; }
  const courseOpts = (sel) => (S.courses.length ? sortedCourses() : [{ id: "", name: t("no_course_yet") }])
    .map((c) => `<option value="${esc(c.id)}" ${c.id === sel ? "selected" : ""}>${esc(c.name)}</option>`).join("") +
    `<option value="__new">+ ${t("new_course")}</option>`;
  box.innerHTML = `
    <div class="block-title">${t("to_add")}</div>
    <div class="add-rows">${picked.map((p, i) => `
      <div class="add-row">
        <span class="file" title="${esc(p.path)}">${esc(p.name)}</span>
        <label class="form-field">${t("title")}<input type="text" data-f="title" data-i="${i}" value="${esc(p.title)}" placeholder="${t("title_ph")}"></label>
        <label class="form-field">${t("date")}<input type="date" data-f="date" data-i="${i}" value="${esc(p.date)}"></label>
        <label class="form-field">${t("course")}<select data-f="course" data-i="${i}">${courseOpts(p.course)}</select></label>
        <label class="form-field" title="${t("spoken_hint")}">${t("spoken")}<select data-f="language" data-i="${i}">
          <option value="nl" ${p.language !== "en" ? "selected" : ""}>Nederlands</option>
          <option value="en" ${p.language === "en" ? "selected" : ""}>English</option></select></label>
        <button type="button" class="icon-btn" data-unpick="${i}" aria-label="${t("remove")}">${ICON.x}</button>
      </div>`).join("")}</div>
    <div class="add-options">
      <div>
        <div class="block-title">${t("slides")}</div>
        <p class="muted small" style="margin:4px 0 10px">${t("slides_hint")}</p>
        <input type="search" id="slide-q" placeholder="${t("slides_search")}" style="margin-bottom:10px">
        <div class="chips chips-wrap" id="slide-chips"></div>
      </div>
      <div>
        <div class="block-title">${t("notes_when")}</div>
        <div class="segmented" id="policy" style="margin:10px 0 8px">
          ${["now", "tonight", "never"].map((v) => `<button type="button" data-v="${v}" aria-pressed="${notesPolicy === v}">${t("notes_" + v)}</button>`).join("")}
        </div>
        <p class="muted small" id="policy-hint">${t("notes_" + notesPolicy + "_hint")}</p>
      </div>
    </div>
    <div class="add-foot">
      <span class="error" id="add-error"></span>
      <button type="button" class="btn" id="add-cancel">${t("cancel")}</button>
      <button type="button" class="btn btn-primary" id="add-go">${picked.length > 1 ? t("add_n", { n: picked.length }) : t("add_1")}</button>
    </div>`;
  $$("[data-f]", box).forEach((el) => el.addEventListener("input", () => {
    if (el.value === "__new") {  // make a course right here instead of a trip to Setup
      const p = picked[el.dataset.i];
      el.value = p.course;
      inlineEdit(el, "", async (name) => {
        const r = await post("/api/courses", { name, language: p.language || "nl" });  // the spoken language, not the app's
        S.courses = await api("/api/courses");
        picked.forEach((x) => { if (x === p || !x.course) x.course = r.id; });
        lastCourse = r.id;
        toast(t("course_added", { name }));
      }, t("new_course_ph"), drawPending);  // redraw: the new course goes into every row's list
      return;
    }
    picked[el.dataset.i][el.dataset.f] = el.value;
    if (el.dataset.f === "course") {
      picked[el.dataset.i].language = courseLang(el.value);
      $(`[data-f="language"][data-i="${el.dataset.i}"]`, box).value = picked[el.dataset.i].language;
      lastCourse = el.value;
      try { localStorage.setItem("lt-course", el.value); } catch { /* ignore */ }
      drawSlideChips();
    }
  }));
  $$("[data-unpick]", box).forEach((b) => b.addEventListener("click", () => { picked.splice(Number(b.dataset.unpick), 1); drawRecent(); drawPending(); }));
  $$("#policy button", box).forEach((b) => b.addEventListener("click", () => {
    notesPolicy = b.dataset.v;
    $$("#policy button", box).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    $("#policy-hint").textContent = t("notes_" + notesPolicy + "_hint");
  }));
  $("#slide-q").addEventListener("input", drawSlideChips);
  $("#add-cancel").addEventListener("click", () => { picked = []; pickedSlides = []; drawRecent(); drawPending(); });
  $("#add-go").addEventListener("click", submitAdd);
  drawSlideChips();
}

function drawSlideChips() {
  const box = $("#slide-chips");
  if (!box) return;
  const chosen = new Set(pickedSlides);
  const q = ($("#slide-q").value || "").trim().toLowerCase();
  const course = picked[0]?.course || lastCourse;
  const all = suggestions?.slides || [];
  const sel = pickedSlides.map((p) => all.find((s) => s.path === p) || { path: p, name: p.split("/").pop() });
  const rest = all.filter((s) => !chosen.has(s.path) && (!q || s.name.toLowerCase().includes(q)))
    .sort((a, b) => (b.course === course) - (a.course === course) || (b.course != null) - (a.course != null) || b.mtime - a.mtime);
  box.innerHTML = [...sel, ...rest.slice(0, q ? 30 : 6)].map((s) => `
    <button type="button" class="chip" aria-pressed="${chosen.has(s.path)}" data-slide="${esc(s.path)}" title="${esc(s.path)}">${chosen.has(s.path) ? "✓ " : ""}${esc(s.name)}${s.course && !chosen.has(s.path) ? ` · ${t("used_before")}` : ""}</button>`).join("")
    + (q && !rest.length ? `<span class="muted small">${t("no_match")}</span>` : "");
  $$("[data-slide]", box).forEach((c) => c.addEventListener("click", () => {
    const p = c.dataset.slide;
    pickedSlides = chosen.has(p) ? pickedSlides.filter((x) => x !== p) : [...pickedSlides, p];
    drawSlideChips();
  }));
}

async function submitAdd() {
  if (picked.some((p) => !p.course)) { $("#add-error").textContent = S.courses.length ? t("choose_course") : t("no_course_yet"); return; }
  try {
    const r = await post("/api/queue", picked.map((p) => ({ media: p.path, course: p.course, slides: pickedSlides, title: p.title, date: p.date, notes: notesPolicy, language: p.language })));
    toast(t("added", { n: r.added.length }));
    picked = []; pickedSlides = []; suggestions = null;
    location.hash = "#/progress";  // follow them in the library
  } catch (e) { $("#add-error").textContent = e.message; }
}
