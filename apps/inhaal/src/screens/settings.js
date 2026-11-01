import { icon } from "@studie/design/icons.js";
import { state } from "../db/store.js";
import { sync } from "../sync/index.js";
import { langChoice, t, themeChoice, timeOf } from "../i18n/index.js";
import { esc } from "../ui/dom.js";

const dateField = (key, label) => `<label class="row"><span class="row-main"><span>${esc(label)}</span></span>
  <input class="field field-compact" type="date" value="${esc(state.semester[key])}" data-semester="${key}"></label>`;

const actionRow = (action, label, extra = "") => `<li><button class="row ${extra}" data-action="${action}"><span class="row-main"><span>${esc(label)}</span></span></button></li>`;

export function syncStatusText() {
  if (sync.status === "ok") return t("syncOk", { time: timeOf(sync.lastAt) });
  if (sync.status === "offline") return t("syncOffline", { n: sync.pending });
  if (sync.status === "badCode") return t("syncBadCode");
  return t("syncNotConnected");
}

const syncSection = () => (sync.available ? `<section>
      <h2 class="group-title">${esc(t("sync"))}</h2>
      <div class="card flow-tight">
        <p class="sub" id="sync-status" aria-live="polite">${esc(syncStatusText())}</p>
        ${sync.status === "ok" ? "" : `<label class="group-label" for="sync-code">${esc(t("syncCode"))}</label>
        <input class="field" id="sync-code" autocomplete="off" autocapitalize="off" spellcheck="false">
        <button class="btn btn-primary btn-block" data-action="sync-connect">${esc(t("syncConnect"))}</button>`}
      </div>
    </section>` : "");

export function renderSettings(root) {
  const semester = state.semester;
  const lecture = state.courses[0]?.minutesPerLecture ?? 120;
  const exercise = state.courses[0]?.minutesPerExercise ?? 150;
  root.innerHTML = `<main class="page">
    <h1 class="large-title">${esc(t("settings"))}</h1>
    <div class="settings-grid">
    ${syncSection()}
    ${semester ? `<section>
      <h2 class="group-title">${esc(semester.name)}</h2>
      <div class="list">${dateField("startDate", t("semesterStart"))}${dateField("endDate", t("semesterEnd"))}${dateField("examStart", t("examStart"))}</div>
    </section>
    <section>
      <h2 class="group-title">${esc(t("manageCourses"))}</h2>
      <ul class="list">${state.courses.map((c) => `<li><button class="row" data-course="${esc(c.colorKey)}" data-edit-course="${esc(c.id)}">
        <span class="dot"></span><span class="row-main"><span>${esc(c.name)}</span></span>
        <span class="row-trail">${c.hidden ? esc(t("hidden")) : esc(c.shortName)}${icon("chevron")}</span></button></li>`).join("")}</ul>
    </section>
    <section>
      <h2 class="group-title">${esc(t("durations"))}</h2>
      <div class="list">
        <label class="row"><span class="row-main"><span>${esc(t("durationLecture"))}</span></span>
          <input class="field field-compact" type="number" inputmode="numeric" min="1" value="${lecture}" data-duration="minutesPerLecture"></label>
        <label class="row"><span class="row-main"><span>${esc(t("durationExercise"))}</span></span>
          <input class="field field-compact" type="number" inputmode="numeric" min="1" value="${exercise}" data-duration="minutesPerExercise"></label>
      </div>
    </section>` : ""}
    <section>
      <h2 class="group-title">${esc(t("data"))}</h2>
      <ul class="list">
        ${actionRow("upload", t("uploadRooster"))}
        ${semester ? actionRow("notes", t("importNotes")) : ""}
        ${semester ? actionRow("export-json", t("exportJson")) : ""}
        ${semester ? actionRow("export-notes", t("exportNotes")) : ""}
        ${actionRow("import-json", t("importJson"))}
        ${semester ? actionRow("erase", t("eraseAll"), "row-danger") : ""}
      </ul>
    </section>
    <section>
      <h2 class="group-title">${esc(t("appearance"))}</h2>
      <div class="segmented" role="group" aria-label="${esc(t("appearance"))}">
        ${[["system", t("themeSystem")], ["light", t("themeLight")], ["dark", t("themeDark")]].map(([key, label]) =>
          `<button aria-pressed="${themeChoice() === key}" data-theme-choice="${key}">${esc(label)}</button>`).join("")}
      </div>
    </section>
    <section class="only-wide">
      <h2 class="group-title">${esc(t("shortcuts"))}</h2>
      <p class="sub">${esc(t("shortcutsBody"))}</p>
    </section>
    <section>
      <h2 class="group-title">${esc(t("language"))}</h2>
      <div class="segmented" role="group" aria-label="${esc(t("language"))}">
        ${[["auto", t("languageAuto")], ["nl", "Nederlands"], ["en", "English"]].map(([key, label]) =>
          `<button aria-pressed="${langChoice() === key}" data-lang="${key}">${esc(label)}</button>`).join("")}
      </div>
    </section>
    </div>
  </main>`;
}
