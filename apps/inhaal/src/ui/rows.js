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
      </button>
      <span class="row-trail">${status === "inProgress" && session.progressSec ? esc(duration(session.progressSec / 60)) : esc(duration(sessionMinutes(session, course)))}</span>
    </div>
  </li>`;
}

export const numbersNow = () => computeNumbers(state.sessions);
