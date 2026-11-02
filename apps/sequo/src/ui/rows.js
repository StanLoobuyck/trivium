// Een sessierij, gedeeld door vakdetail en de chronologische lijst.
import { icon } from "@studie/design/icons.js";
import { computeNumbers, effectiveStatus, isDone, sessionMinutes } from "../domain/sessions.js";
import { courseById, state } from "../db/store.js";
import { duration, shortDate, t } from "../i18n/index.js";
import { esc } from "./dom.js";

export function sessionTitle(session, numbers = computeNumbers(state.sessions)) {
  const number = numbers.get(session.id);
  const key = { lecture: "lecture", exercise: "exercise", lab: "lab" }[session.type];
  return number && key ? t(key, { n: number }) : t("extra");
}

// Halverwege: de rij toont wat overblijft, deze regel wat al bekeken is.
export const progressText = (session) => (session.status === "inProgress" && session.progressSec
  ? t("inProgress", { time: duration(session.progressSec / 60) }) : "");

export const notesText = (session) => (session.verbatimJob ? t(session.notesKind === "transcript" ? "transcriptReady" : "notesReady") : "");

// Verbatim draait op de eigen laptop.
export const verbatimLink = (session) => `http://127.0.0.1:7861/#/lecture/${encodeURIComponent(session.verbatimJob)}`;

export const sessionLabel = (session, numbers) => `${sessionTitle(session, numbers)} · ${shortDate(new Date(session.start))}`;

export function sessionRow(session, { numbers, now, showCourse = false, selecting = null }) {
  const course = courseById(session.courseId);
  const status = effectiveStatus(session, now);
  if (status === "cancelled") {
    return `<li><div class="row is-done" data-flip="${esc(session.id)}">
      <button class="row-main row-link" data-options="${esc(session.id)}"><span>${esc(shortDate(new Date(session.start)))} · ${esc(t("cancelled"))}</span></button></div></li>`;
  }
  const label = sessionLabel(session, numbers);
  const done = isDone(session, now);
  const picked = selecting?.has(session.id);
  const checked = selecting ? picked : done;
  const verb = t(done ? "untick" : "tick", { label });
  return `<li class="swipe" data-course="${esc(course.colorKey)}" data-swipe="${esc(session.id)}">
    <div class="swipe-under" aria-hidden="true">${icon("check")}${icon("more")}</div>
    <div class="row" data-flip="${esc(session.id)}">
      <button class="check" role="checkbox" aria-checked="${checked}" aria-label="${esc(verb)}" data-${selecting ? "pick" : "tick"}="${esc(session.id)}"><span class="check-mark">${icon("check")}</span></button>
      <button class="row-main row-link" data-options="${esc(session.id)}">
        <span>${esc(label)}</span>
        ${showCourse ? `<span class="sub">${esc(course.name)}</span>` : ""}
        ${progressText(session) ? `<span class="sub">${esc(progressText(session))}</span>` : ""}
        ${notesText(session) ? `<span class="sub">${esc(notesText(session))}</span>` : ""}
      </button>
      <span class="row-trail">${esc(duration(sessionMinutes(session, course)))}</span>
    </div>
  </li>`;
}

export const numbersNow = () => computeNumbers(state.sessions);
