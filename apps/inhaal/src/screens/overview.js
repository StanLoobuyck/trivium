import { icon } from "@studie/design/icons.js";
import { missingWeeks } from "../domain/rooster.js";
import { needsBackupReminder, summarize } from "../domain/sessions.js";
import { courseById, state } from "../db/store.js";
import { t } from "../i18n/index.js";
import { esc } from "../ui/dom.js";
import { numbersNow, sessionLabel, sessionRow } from "../ui/rows.js";

export const view = { mode: "course", filter: "all" };

const isStandalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent);

const counts = (p) => [
  p.lecture && `${p.lecture} ${t("hc")}`,
  p.exercise && `${p.exercise} ${t("oz")}`,
  p.lab && `${p.lab} ${t("labShort")}`,
].filter(Boolean).join(" · ");

function notices(now) {
  const parts = [];
  const weeks = missingWeeks(state.semester.startDate, state.sessions);
  if (weeks > 0 && !state.meta.weeksDismissed) {
    parts.push(`<div class="banner"><span>${esc(t("missingWeeks", { n: weeks }))}</span>
      <span class="banner-actions"><button class="btn btn-small btn-plain" data-action="upload">${esc(t("uploadRooster"))}</button>
      <button class="btn btn-small btn-plain" data-action="dismiss-weeks">${esc(t("dismiss"))}</button></span></div>`);
  }
  if (state.meta.firstUseAt && needsBackupReminder(state.meta.lastBackupAt, state.meta.firstUseAt, now)) {
    parts.push(`<div class="banner"><span>${esc(t("backupReminder"))}</span>
      <button class="btn btn-small btn-plain" data-action="export-json">${esc(t("backupNow"))}</button></div>`);
  }
  if (!isStandalone() && !state.meta.installDismissed) {
    parts.push(`<div class="banner"><span><strong>${esc(t("installTitle"))}</strong><br>${esc(t(isIos() ? "installIos" : "installOther"))}</span>
      <button class="btn btn-small btn-plain" data-action="dismiss-install">${esc(t("dismiss"))}</button></div>`);
  }
  return parts.join("");
}

function hero(summary) {
  const hours = Math.round(summary.minutes / 60);
  return `<section class="hero">
    <span class="hero-number" data-testid="open-count">${summary.open}</span>
    <span class="sub">${esc(t(summary.open === 1 ? "oneSessionHours" : "sessionsHours", { hours }))}</span>
    <div class="progress" role="img" aria-label="${Math.round(summary.progress * 100)}%"><span style="--value: ${summary.progress}"></span></div>
  </section>`;
}

function nextCard(summary) {
  if (!summary.next) return "";
  const course = courseById(summary.next.courseId);
  return `<section class="card" data-course="${esc(course.colorKey)}">
    <p class="label">${esc(t("next"))}</p>
    <div class="row row-flush">
      <span class="dot"></span>
      <div class="row-main"><div>${esc(sessionLabel(summary.next, numbersNow()))}</div><div class="sub">${esc(course.name)}</div></div>
      <button class="btn btn-small btn-primary" data-tick="${esc(summary.next.id)}">${esc(t("watched"))}</button>
    </div>
  </section>`;
}

function segmented(name, options, value) {
  return `<div class="segmented" role="group" aria-label="${esc(name)}">${options.map(([key, label]) =>
    `<button aria-pressed="${key === value}" data-view="${esc(name)}:${key}">${esc(label)}</button>`).join("")}</div>`;
}

function courseList(summary) {
  return `<ul class="list">${summary.perCourse.map((p) => `<li>
    <a class="row ${!p.open && p.done ? "is-done" : ""}" href="#/vak/${esc(p.course.id)}" data-course="${esc(p.course.colorKey)}">
      <span class="dot"></span>
      <span class="row-main"><span>${esc(p.course.name)}</span></span>
      <span class="row-trail">${p.open ? esc(counts(p)) : p.done ? icon("check") : ""}${icon("chevron")}</span>
    </a></li>`).join("")}</ul>`;
}

function chronological(summary, now) {
  const numbers = numbersNow();
  const list = summary.openSessions.filter((s) => view.filter === "all" || s.type === view.filter);
  if (!list.length) return `<div class="empty">${icon("check")}<span>${esc(t("allCaughtUp"))}</span></div>`;
  return `<ul class="list">${list.map((s) => sessionRow(s, { numbers, now, showCourse: true })).join("")}</ul>`;
}

export function renderOverview(root, now) {
  if (!state.semester) {
    root.innerHTML = `<main class="page">
      <h1 class="large-title">${esc(t("appTitle"))}</h1>
      <section class="card empty">
        ${icon("calendar")}
        <h2 class="title">${esc(t("emptyTitle"))}</h2>
        <p class="sub">${esc(t("emptyBody"))}</p>
        <button class="btn btn-primary" data-action="upload">${esc(t("uploadRooster"))}</button>
      </section>
    </main>`;
    return;
  }
  const summary = summarize(state.courses, state.sessions, now);
  const mode = segmented(t("perCourse"), [["course", t("perCourse")], ["list", t("chronological")]], view.mode);
  const filter = view.mode === "list"
    ? segmented(t("type"), [["all", t("all")], ["lecture", t("hc")], ["exercise", t("oz")], ["lab", t("labShort")]], view.filter) : "";
  root.innerHTML = `<main class="page">
    <h1 class="large-title">${esc(t("appTitle"))}</h1>
    ${notices(now)}
    <div class="overview-top">${hero(summary)}${nextCard(summary)}</div>
    <section class="stack-tight">${mode}${filter}</section>
    ${view.mode === "course" ? courseList(summary) : chronological(summary, now)}
  </main>`;
}
