import { icon } from "@studie/design/icons.js";
import { effectiveStatus, isDone, isOpen, visibleSessions } from "../domain/sessions.js";
import { courseById, state } from "../db/store.js";
import { t } from "../i18n/index.js";
import { esc } from "../ui/dom.js";
import { numbersNow, sessionRow } from "../ui/rows.js";

export const courseView = { filter: "all", finishedOpen: false, selecting: null };

export function renderCourse(root, id, now) {
  const course = courseById(id);
  if (!course) { location.hash = "#/"; return; }
  const own = state.sessions.filter((s) => s.courseId === id).sort((a, b) => a.start.localeCompare(b.start));
  const countable = visibleSessions([{ ...course, hidden: false }], own);
  const types = [["all", t("all")], ["lecture", t("hc")], ["exercise", t("oz")]];
  if (own.some((s) => s.type === "lab")) types.push(["lab", t("labShort")]);
  const match = (s) => courseView.filter === "all" || s.type === courseView.filter;

  const numbers = numbersNow();
  const options = { numbers, now, selecting: courseView.selecting };
  const visible = own.filter(match);
  const open = visible.filter((s) => isOpen(s, now) || effectiveStatus(s, now) === "cancelled");
  const finished = visible.filter((s) => isDone(s, now));
  const done = countable.filter((s) => isDone(s, now)).length;
  const past = countable.filter((s) => isDone(s, now) || isOpen(s, now)).length;
  const value = past ? done / past : 0;

  root.innerHTML = `<main class="page">
    <div class="course-nav">
      <a class="btn btn-plain" href="#/" aria-label="${esc(t("overview"))}"><span class="flip-icon">${icon("chevron")}</span></a>
      ${courseView.selecting ? `<button class="btn btn-plain" data-action="select-cancel">${esc(t("cancel"))}</button>` : `<button class="btn btn-plain" data-action="select">${esc(t("select"))}</button>`}
    </div>
    <header class="course-head" data-course="${esc(course.colorKey)}">
      <div>
        <h1 class="title">${esc(course.name)}</h1>
        <p class="sub">${esc(course.shortName)} · ${done} / ${past}</p>
      </div>
      <div class="ring" style="--value: ${value}" role="img" aria-label="${Math.round(value * 100)}%"></div>
    </header>
    <div class="segmented" role="group" aria-label="${esc(t("type"))}">${types.map(([key, label]) =>
      `<button aria-pressed="${courseView.filter === key}" data-filter="${key}">${esc(label)}</button>`).join("")}</div>
    ${open.length ? `<ul class="list">${open.map((s) => sessionRow(s, options)).join("")}</ul>`
      : `<div class="empty">${icon("check")}<span>${esc(t("allCaughtUp"))}</span></div>`}
    ${finished.length ? `<details class="finished" ${courseView.finishedOpen ? "open" : ""}>
      <summary class="group-title">${esc(t("finished", { n: finished.length }))}</summary>
      <ul class="list">${finished.map((s) => sessionRow(s, { numbers, now })).join("")}</ul>
    </details>` : ""}
    ${courseView.selecting?.size ? `<button class="btn btn-primary btn-block select-bar" data-action="tick-selected">${esc(t("tickSelected", { n: courseView.selecting.size }))}</button>` : ""}
  </main>`;
}
