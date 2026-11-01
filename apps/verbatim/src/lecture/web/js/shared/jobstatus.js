// How a queue item's progress and status read: step bar (Audio · Transcript · Slides · Notes), status text, pill.
import { when } from "../core/format.js";

const STEP_OF_STAGE = { audio: 0, player: 0, slides: 1, chunk: 1, transcribe: 1, stitch: 1, sections: 2, study_pack: 2, review: 2, notes: 3 };

export function stepsHtml(i) {
  // which of Audio · Transcript · Slides · Notes is done / running / waiting
  let current = -1;
  if (i.status === "transcribing") current = STEP_OF_STAGE[i.stage] ?? 0;
  if (["transcribed", "notes_pending", "notes"].includes(i.status)) current = 3;
  if (i.status === "failed") current = i.failed_at === "notes" ? 3 : (STEP_OF_STAGE[i.stage] ?? 0);
  const names = ["step_audio", "step_transcript", "step_slides", "step_notes"];
  return `<div class="steps">${names.map((n, k) => {
    let cls = "", bar = "";
    if (k === 3 && i.notes === "never") cls = "skip";
    else if (i.status === "queued") cls = "";
    else if (k < current) cls = "done";
    else if (k === current) {
      cls = i.status === "failed" ? "" : "now";
      const pct = i.stage === "transcribe" && i.progress != null && i.status === "transcribing" ? Math.round(i.progress * 100) : null;
      bar = ["transcribing", "notes"].includes(i.status) ? (pct != null ? `<span style="width:${pct}%"></span>` : `<span class="indet"></span>`) : "";
    }
    return `<div class="step ${cls}"><span>${t(n)}</span><div class="bar">${bar || (cls === "done" ? "<span></span>" : "")}</div></div>`;
  }).join("")}</div>`;
}

export function statusText(i) {
  switch (i.status) {
    case "queued": return i.resume_at ? t("st_waiting_until", { when: when(i.resume_at) }) : t("st_queued");
    case "transcribing": {
      const pct = i.stage === "transcribe" && i.progress != null ? ` · ${Math.round(i.progress * 100)}%` : "";
      return (t("stage_" + i.stage) || t("st_transcribing")) + pct;
    }
    case "transcribed": return i.notes === "tonight" ? t("st_transcribed_tonight") : t("st_transcribed");
    case "notes": return t("st_notes");
    case "notes_pending": return i.resume_at ? t("st_notes_pending_until", { when: when(i.resume_at) }) : t("st_notes_pending");
    case "failed": return t("st_failed");
    default: return t("st_done");
  }
}
export const pillClass = (st) => ({ transcribing: "active", notes: "active", transcribed: "wait", notes_pending: "wait", failed: "bad", done: "ok" }[st] || "");

// Thin progress bar + the step names below it (done steps in text colour, the current one bold), as in the design
export function progressHtml(i) {
  let current = -1;
  if (i.status === "transcribing") current = STEP_OF_STAGE[i.stage] ?? 0;
  if (["transcribed", "notes_pending", "notes"].includes(i.status)) current = 3;
  if (i.status === "failed") current = i.failed_at === "notes" ? 3 : (STEP_OF_STAGE[i.stage] ?? 0);
  const pct = i.stage === "transcribe" && i.progress != null && i.status === "transcribing" ? Math.round(i.progress * 100) : null;
  const running = ["transcribing", "notes"].includes(i.status);
  const bar = pct != null ? `<span style="width:${pct}%"></span>` : running ? `<span class="indet"></span>` : "";
  const names = ["step_audio", "step_transcript", "step_slides", "step_notes"];
  const steps = names.map((n, k) => {
    const cls = k === 3 && i.notes === "never" ? "skip" : i.status === "queued" ? "" : k < current ? "done" : k === current ? "now" : "";
    return `<span class="${cls}">${t(n)}</span>`;
  }).join("");
  return `<div class="prog-bar" role="progressbar" ${pct != null ? `aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"` : ""}
    aria-label="${t("progress")}">${bar}</div><div class="prog-steps">${steps}</div>`;
}
