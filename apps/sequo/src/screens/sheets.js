// Alle sheets: toevoegen, sessie-opties, importcontrole, vak bewerken, Notes en bevestigingen.
import { addDays, startOfDay } from "date-fns";
import { COLORS, mergeProposal, proposeCourses, proposeMerges, byName } from "../domain/courses.js";
import { parseNotes, planNotesImport } from "../domain/notes.js";
import { currentCluster, parseRooster, proposeSemester, splitSemesters } from "../domain/rooster.js";
import { readBackup } from "../domain/backup.js";
import { COUNTED_TYPES, isOpen } from "../domain/sessions.js";
import { lectureParts, partState } from "../domain/recordings.js";
import * as store from "../db/store.js";
import { chipDate, duration, t } from "../i18n/index.js";
import { $, $$, esc, pickFiles } from "../ui/dom.js";
import { closeSheet, openSheet, toast } from "../ui/feedback.js";
import { numbersNow, progressText, sessionLabel, verbatimLink } from "../ui/rows.js";

const { state } = store;
let refresh = () => {};
export const setRefresh = (fn) => { refresh = fn; };

const nextColor = (key) => COLORS[(COLORS.indexOf(key) + 1) % COLORS.length];
const pad = (n) => String(n).padStart(2, "0");
const dateValue = (iso) => { const d = new Date(iso); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };

// ---- Toevoegen ----
export function openAdd() {
  const courses = state.courses.filter((c) => !c.hidden).sort(byName);
  if (!courses.length) return;
  const today = startOfDay(new Date());
  const days = Array.from({ length: 21 }, (_, i) => addDays(today, -i));
  const choice = {
    courseId: courses.some((c) => c.id === state.meta.lastCourseId) ? state.meta.lastCourseId : courses[0].id,
    type: "lecture",
    dates: new Set(),
  };
  const chips = (key, options, on) => options.map(([value, label]) =>
    `<button class="chip" aria-pressed="${on(value)}" data-${key}="${esc(value)}">${esc(label)}</button>`).join("");
  const draw = () => {
    const sheet = openSheet(`<h2 class="title">${esc(t("add"))}</h2>
      <p class="group-label">${esc(t("course"))}</p>
      <div class="chips">${chips("pick-course", courses.map((c) => [c.id, c.shortName]), (v) => v === choice.courseId)}</div>
      <p class="group-label">${esc(t("type"))}</p>
      <div class="chips">${chips("pick-type", [["lecture", t("typeLecture")], ["exercise", t("typeExercise")], ["lab", t("typeLab")]], (v) => v === choice.type)}</div>
      <p class="group-label">${esc(t("dates"))}</p>
      <div class="chips">${chips("pick-date", days.map((d, i) => [String(i), i ? chipDate(d) : t("today")]), (v) => choice.dates.has(v))}</div>
      <button class="btn btn-primary btn-block sheet-action" data-confirm ${choice.dates.size ? "" : "disabled"}>${esc(t("addN", { n: choice.dates.size }))}</button>`, t("add"));
    sheet.onclick = async (e) => {
      const button = e.target.closest("button");
      if (!button) return;
      if (button.dataset.pickCourse) choice.courseId = button.dataset.pickCourse;
      else if (button.dataset.pickType) choice.type = button.dataset.pickType;
      else if (button.dataset.pickDate) {
        const key = button.dataset.pickDate;
        if (choice.dates.has(key)) choice.dates.delete(key); else choice.dates.add(key);
      } else if ("confirm" in button.dataset) {
        const course = store.courseById(choice.courseId);
        const minutes = choice.type === "lecture" ? course.minutesPerLecture : course.minutesPerExercise;
        const now = new Date();
        const ends = [...choice.dates].map((i) => (i === "0" ? now : new Date(+addDays(today, -i) + 20 * 3600000)));
        await store.addManualSessions({ courseId: choice.courseId, type: choice.type, dates: ends, minutes });
        const count = ends.length;
        closeSheet();
        refresh();
        toast(t("added", { n: count }));
        return;
      } else return;
      draw();
    };
  };
  draw();
}

// ---- Sessie-opties ----
function partText(part) {
  const state = partState(part);
  if (state === "watched") return t("partWatched", { time: duration(part.durationSec / 60) });
  if (state === "progress") {
    const done = duration(part.watchedSec / 60);
    return part.durationSec ? t("partProgress", { done, total: duration(part.durationSec / 60) }) : t("partStarted", { done });
  }
  return t("partNotWatched");
}

function partsHtml(parts) {
  return `<p class="group-label">${esc(t("parts"))}</p>
    <ul class="list list-inset">${parts.map((p) => `<li><div class="row">
      <span class="row-main"><span>${esc(t("part", { n: p.number }))}</span><span class="sub">${esc(partText(p))}</span></span>
      <span class="row-trail">
        ${p.url ? `<a class="btn btn-small" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(t("partRecording"))}</a>` : ""}
        ${p.verbatimJob ? `<a class="btn btn-small only-wide" href="${esc(verbatimLink(p))}" target="_blank" rel="noopener">Verbatim</a>` : ""}
      </span></div></li>`).join("")}</ul>`;
}

export function openOptions(id) {
  const session = store.sessionById(id);
  if (!session) return;
  const course = store.courseById(session.courseId);
  const label = sessionLabel(session, numbersNow());
  const statuses = [["watched", "statusWatched"], ["processed", "statusProcessed"], ["attended", "statusAttended"], ["cancelled", "statusCancelled"], ["skipped", "statusSkipped"], ["upcoming", "statusMissed"]];
  const recording = session.recordings?.[0];
  const link = recording?.url ?? "";
  // Een les in delen (Velox): per deel hoe ver je bent, de opname en de Verbatim-les. Dan geen los linkveld.
  const parts = lectureParts(session);
  const sheet = openSheet(`<h2 class="title">${esc(label)}</h2>
    <p class="sub">${esc(course.name)}${session.location ? ` · ${esc(session.location)}` : ""}</p>
    ${progressText(session) ? `<p class="sub">${esc(progressText(session))}</p>` : ""}
    <p class="group-label">${esc(t("statusTitle"))}</p>
    <div class="chips chips-wrap">${statuses.map(([value, key]) =>
      `<button class="chip" aria-pressed="${session.status === value}" data-status="${value}">${esc(t(key))}</button>`).join("")}</div>
    <p class="group-label"><label for="session-note">${esc(t("note"))}</label></p>
    <textarea class="field" id="session-note" rows="2">${esc(session.note)}</textarea>
    ${parts.length ? partsHtml(parts) : `<p class="group-label"><label for="session-link">${esc(t("recordingLink"))}</label></p>
    <input class="field" id="session-link" type="url" inputmode="url" value="${esc(link)}">
    ${link ? `<a class="btn btn-block sheet-action" href="${esc(link)}" target="_blank" rel="noopener">${esc(t("openRecording"))}</a>` : ""}
    ${session.verbatimJob ? `<a class="btn btn-block sheet-action only-wide" href="${esc(verbatimLink(session))}" target="_blank" rel="noopener">${esc(t("openVerbatim"))}</a>` : ""}
    ${recording?.fileName ? `<p class="sub">${esc(t("downloadedAs", { name: recording.fileName }))}</p>` : ""}`}
    <p class="group-label"><label for="session-date">${esc(t("date"))}</label></p>
    <input class="field" id="session-date" type="date" value="${dateValue(session.start)}">
    <div class="sheet-split">
      <button class="btn btn-danger" data-delete>${esc(t("delete"))}</button>
      <button class="btn btn-primary" data-close>${esc(t("done"))}</button>
    </div>`, label);

  const save = async () => {
    const note = $("#session-note", sheet).value.trim() || null;
    const changes = { note };
    if (!parts.length) {
      const url = $("#session-link", sheet).value.trim();
      changes.recordings = url ? [{ ...recording, url }, ...(session.recordings ?? []).slice(1)] : [];
    }
    const date = $("#session-date", sheet).value;
    if (date && date !== dateValue(session.start)) {
      const shift = new Date(`${date}T12:00:00`) - new Date(`${dateValue(session.start)}T12:00:00`);
      changes.start = new Date(new Date(session.start).getTime() + shift).toISOString();
      changes.end = new Date(new Date(session.end).getTime() + shift).toISOString();
    }
    await store.updateSession(id, changes);
  };

  sheet.onclick = async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if (button.dataset.status) {
      await save();
      const undo = await store.setStatus([id], button.dataset.status);
      closeSheet();
      refresh();
      toast(t(statuses.find(([v]) => v === button.dataset.status)[1]), async () => { await undo(); refresh(); });
    } else if ("delete" in button.dataset) {
      const undo = await store.deleteSession(id);
      closeSheet();
      refresh();
      toast(t("deleted"), async () => { await undo(); refresh(); });
    } else if ("close" in button.dataset) {
      await save();
      closeSheet();
      refresh();
    }
  };
}

// ---- Rooster ----
export async function uploadRooster() {
  const files = await pickFiles(".ics,text/calendar", true);
  if (files.length) await importFiles(files);
}

export async function importFiles(files) {
  let events;
  try {
    const texts = await Promise.all(files.map((f) => f.text()));
    events = texts.flatMap(parseRooster).sort((a, b) => a.start.localeCompare(b.start));
  } catch {
    toast(t("badFile"));
    return;
  }
  if (!events.length) { toast(t("noRoosterEvents")); return; }

  const clusters = splitSemesters(events);
  const semester = state.semester;
  const inSemester = semester && clusters.find((c) => c[0].start.slice(0, 10) <= semester.endDate && c.at(-1).end.slice(0, 10) >= semester.startDate);
  if (inSemester) {
    const { added, updated, vanished } = await store.applyRooster(inSemester);
    refresh();
    toast(t("importResult", { added, updated }));
    if (vanished.length) openVanished(vanished);
    return;
  }
  openReview(currentCluster(clusters, new Date()));
}

function openReview(cluster) {
  let courses = proposeCourses(cluster);
  const ignored = new Set();
  const draw = () => {
    const merges = proposeMerges(courses, cluster).filter(([a, b]) => !ignored.has(`${a}|${b}`));
    const sheet = openSheet(`<h2 class="title">${esc(t("reviewTitle"))}</h2>
      <p class="sub">${esc(t("reviewBody"))} ${esc(t("importedSessions", { n: cluster.length }))}</p>
      ${merges.map(([a, b]) => `<div class="banner sheet-banner"><span>${esc(t("mergeHint", { a, b }))}</span>
        <span class="banner-actions"><button class="btn btn-small btn-plain" data-merge="${esc(a)}|${esc(b)}">${esc(t("merge"))}</button>
        <button class="btn btn-small btn-plain" data-ignore="${esc(a)}|${esc(b)}">${esc(t("keep"))}</button></span></div>`).join("")}
      <ul class="list list-inset">${courses.map((c, i) => `<li><div class="row" data-course="${esc(c.colorKey)}">
        <button class="color-button" aria-label="${esc(t("color", { name: c.name }))}" data-color="${i}"><span class="dot"></span></button>
        <div class="row-main"><span>${esc(c.name)}</span></div>
        <input class="field field-short" aria-label="${esc(t("shortName", { name: c.name }))}" value="${esc(c.shortName)}" data-short="${i}">
        <input class="switch" type="checkbox" role="switch" aria-label="${esc(t("show", { name: c.name }))}" ${c.hidden ? "" : "checked"} data-show="${i}">
      </div></li>`).join("")}</ul>
      <button class="btn btn-primary btn-block sheet-action" data-confirm>${esc(t("startSemester"))}</button>`, t("reviewTitle"));

    const syncInputs = () => {
      $$("[data-short]", sheet).forEach((input) => { courses[+input.dataset.short].shortName = input.value.trim() || courses[+input.dataset.short].shortName; });
      $$("[data-show]", sheet).forEach((input) => { courses[+input.dataset.show].hidden = !input.checked; });
    };
    sheet.onclick = async (e) => {
      const button = e.target.closest("button");
      if (!button) return;
      syncInputs();
      if (button.dataset.merge) {
        const [a, b] = button.dataset.merge.split("|");
        courses = mergeProposal(courses, a, b);
      } else if (button.dataset.ignore) {
        ignored.add(button.dataset.ignore);
      } else if (button.dataset.color) {
        const course = courses[+button.dataset.color];
        course.colorKey = nextColor(course.colorKey);
      } else if ("confirm" in button.dataset) {
        await store.createSemester({ semester: proposeSemester(cluster), courses, events: cluster });
        closeSheet();
        location.hash = "#/";
        refresh();
        return;
      } else return;
      draw();
    };
  };
  draw();
}

export function openVanished(sessions) {
  const numbers = numbersNow();
  const sheet = openSheet(`<h2 class="title">${esc(t("vanishedTitle"))}</h2>
    <p class="sub">${esc(t("vanishedBody"))}</p>
    <ul class="list list-inset">${sessions.map((s) => `<li><div class="row"><span class="row-main"><span>${esc(store.courseById(s.courseId)?.shortName)} · ${esc(sessionLabel(s, numbers))}</span></span></div></li>`).join("")}</ul>
    <div class="sheet-split">
      <button class="btn" data-keep>${esc(t("keep"))}</button>
      <button class="btn btn-primary" data-mark>${esc(t("markCancelled"))}</button>
    </div>`, t("vanishedTitle"));
  sheet.onclick = async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if ("mark" in button.dataset) await store.setStatus(sessions.map((s) => s.id), "cancelled");
    closeSheet();
    refresh();
  };
}

// ---- Opname koppelen ----
export function openLinkRecording() {
  const entry = state.meta.unmatchedRecordings[0];
  if (!entry) { closeSheet(); refresh(); return; }
  const course = store.courseById(entry.courseId);
  const numbers = numbersNow();
  const now = new Date();
  const choices = state.sessions.filter((s) => s.courseId === entry.courseId && s.status !== "cancelled" && COUNTED_TYPES.includes(s.type))
    .sort((a, b) => isOpen(b, now) - isOpen(a, now) || a.start.localeCompare(b.start));
  const title = t("linkRecordingTitle", { course: course?.shortName ?? "" });
  const sheet = openSheet(`<h2 class="title">${esc(title)}</h2>
    <p class="sub">${esc(entry.recording.title ?? "")}</p>
    <ul class="list list-inset">${choices.map((s) => `<li><button class="row" data-session="${esc(s.id)}"><span class="row-main"><span>${esc(sessionLabel(s, numbers))}</span></span></button></li>`).join("")}</ul>
    <button class="btn btn-block sheet-action" data-skip>${esc(t("linkRecordingSkip"))}</button>`, title);
  sheet.onclick = async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if ("skip" in button.dataset) await store.dropRecording(entry.key);
    else {
      const { undo } = await store.chooseRecording(entry.key, button.dataset.session);
      if (undo) toast(t("tickedRecording", { label: sessionLabel(store.sessionById(button.dataset.session), numbers) }), async () => { await undo(); refresh(); });
    }
    if (state.meta.unmatchedRecordings.length) { openLinkRecording(); refresh(); } else { closeSheet(); refresh(); }
  };
}

// ---- Vak bewerken ----
export function openCourse(id) {
  const course = store.courseById(id);
  const others = state.courses.filter((c) => c.id !== id).sort(byName);
  const sheet = openSheet(`<h2 class="title">${esc(course.name)}</h2>
    <p class="group-label"><label for="course-name">${esc(t("courseName"))}</label></p>
    <input class="field" id="course-name" value="${esc(course.name)}">
    <p class="group-label"><label for="course-short">${esc(t("shortName", { name: "" }))}</label></p>
    <input class="field" id="course-short" value="${esc(course.shortName)}">
    <div class="chips chips-wrap sheet-action">${COLORS.map((color) => `<button class="color-button" data-course="${color}" aria-label="${esc(color)}" aria-pressed="${color === course.colorKey}" data-set-color="${color}"><span class="dot"></span></button>`).join("")}</div>
    <label class="row row-flush"><span class="row-main"><span>${esc(t("hide"))}</span></span>
      <input class="switch" type="checkbox" role="switch" id="course-hidden" ${course.hidden ? "checked" : ""}></label>
    <p class="group-label">${esc(t("codes"))}</p>
    <ul class="list list-inset">${course.codes.map((code) => `<li><div class="row"><span class="row-main"><span>${esc(code)}</span></span>
      ${course.codes.length > 1 ? `<button class="btn btn-small" data-split="${esc(code)}">${esc(t("split"))}</button>` : ""}</div></li>`).join("")}</ul>
    ${others.length ? `<p class="group-label"><label for="course-merge">${esc(t("mergeWith"))}</label></p>
    <select class="field" id="course-merge"><option value=""></option>${others.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("")}</select>` : ""}
    <button class="btn btn-primary btn-block sheet-action" data-close>${esc(t("done"))}</button>`, course.name);

  let colorKey = course.colorKey;
  const save = () => store.updateCourse(id, {
    name: $("#course-name", sheet).value.trim() || course.name,
    shortName: $("#course-short", sheet).value.trim() || course.shortName,
    hidden: $("#course-hidden", sheet).checked,
    colorKey,
  });

  $("#course-merge", sheet)?.addEventListener("change", async (e) => {
    await save();
    await store.mergeCourses(id, e.target.value);
    closeSheet();
    refresh();
    toast(t("mergeDone"));
  });
  sheet.onclick = async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if (button.dataset.setColor) {
      colorKey = button.dataset.setColor;
      $$("[data-set-color]", sheet).forEach((b) => b.setAttribute("aria-pressed", b === button));
    } else if (button.dataset.split) {
      await save();
      await store.splitCode(id, button.dataset.split);
      closeSheet();
      refresh();
    } else if ("close" in button.dataset) {
      await save();
      closeSheet();
      refresh();
    }
  };
}

// ---- Notes ----
export function openNotes() {
  const sheet = openSheet(`<h2 class="title">${esc(t("notesTitle"))}</h2>
    <p class="sub">${esc(t("notesBody"))}</p>
    <textarea class="field sheet-action" id="notes-text" rows="8" aria-label="${esc(t("notesTitle"))}" placeholder="${esc(t("notesPlaceholder"))}"></textarea>
    <p class="sub sheet-action" id="notes-result" aria-live="polite"></p>
    <div class="sheet-split">
      <button class="btn" data-check>${esc(t("check"))}</button>
      <button class="btn btn-primary" data-import disabled>${esc(t("import"))}</button>
    </div>`, t("notesTitle"));
  let plan = null;
  const importButton = $("[data-import]", sheet);
  sheet.onclick = async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if ("check" in button.dataset) {
      const items = parseNotes($("#notes-text", sheet).value);
      plan = items.length ? planNotesImport(items, state.courses, state.sessions, state.semester) : null;
      importButton.disabled = !plan;
      const lines = plan ? [t("notesPlan", { link: plan.link.length, create: plan.create.length })] : [t("notesEmpty")];
      if (plan?.unknown.length) lines.push(t("notesUnknown", { names: plan.unknown.join(", ") }));
      $("#notes-result", sheet).textContent = lines.join(" · ");
    } else if ("import" in button.dataset && plan) {
      await store.applyNotesPlan(plan);
      closeSheet();
      refresh();
      toast(t("notesDone"));
    }
  };
}

// ---- Bevestigen ----
function confirmSheet(body, action, run) {
  const sheet = openSheet(`<p>${esc(body)}</p>
    <div class="sheet-split">
      <button class="btn" data-close>${esc(t("cancel"))}</button>
      <button class="btn btn-danger" data-run>${esc(action)}</button>
    </div>`, action);
  sheet.onclick = async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if ("run" in button.dataset) await run();
    closeSheet();
    refresh();
  };
}

export function openErase() {
  confirmSheet(t("eraseConfirm"), t("eraseAll"), async () => {
    await store.eraseAll();
    toast(t("erased"));
  });
}

export async function restoreBackup() {
  const [file] = await pickFiles(".json,application/json", false);
  if (!file) return;
  let data;
  try {
    data = readBackup(await file.text());
  } catch {
    toast(t("badFile"));
    return;
  }
  confirmSheet(t("restoreConfirm"), t("restore"), async () => {
    await store.restoreAll(data);
    toast(t("restored"));
  });
}

