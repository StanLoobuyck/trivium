// How a queue item's progress and status read: step bar (Audio · Transcript · Slides · Terms · Notes), status text, pill.
import { when } from "../core/format.js";

const STEP_OF_STAGE = { audio: 0, player: 0, slides: 1, chunk: 1, transcribe: 1, stitch: 1, sections: 2, suggestions: 3, study_pack: 3, review: 3, notes: 4 };
const STEP_NAMES = ["step_audio", "step_transcript", "step_slides", "step_terms", "step_notes"];
const NOTES_STEP = STEP_NAMES.length - 1;
const LATEX_STAGES = ["latex_prepare", "latex_read", "latex_write", "latex_figures", "latex_compile"];

function currentStep(i) {
  if (["transcribed", "notes_pending", "notes"].includes(i.status)) return NOTES_STEP;
  if (i.status === "failed") return i.failed_at === "notes" ? NOTES_STEP : (STEP_OF_STAGE[i.stage] ?? 0);
  return i.status === "transcribing" ? (STEP_OF_STAGE[i.stage] ?? 0) : -1;
}

// How far the current step is, when that step reports it (a step can also just be running).
const stepPct = (i) => (i.status === "transcribing" && i.progress != null ? Math.round(i.progress * 100) : null);

// "chunk 7/40", "part 7/40" in the worker's message → "part 7 of 40" in the user's language.
function partText(i) {
  const m = /(?:chunk|part) (\d+)\/(\d+)/.exec(i.message || "");
  return m ? t("st_part", { n: m[1], total: m[2] }) : "";
}

export function statusText(i) {
  switch (i.status) {
    case "latex_queued": return i.resume_at ? t("st_waiting_until", { when: when(i.resume_at) }) : t("st_queued");
    case "latex": return t("stage_" + i.stage) || t("stage_latex_prepare");
    case "queued": return i.resume_at ? t("st_waiting_until", { when: when(i.resume_at) }) : t("st_queued");
    case "transcribing": {
      const pct = stepPct(i);
      return [t("stage_" + i.stage) || t("st_transcribing"), pct != null ? `${pct}%` : "", pct != null ? partText(i) : ""].filter(Boolean).join(" · ");
    }
    case "transcribed": return i.notes === "tonight" ? t("st_transcribed_tonight") : t("st_transcribed");
    case "notes": return t("st_notes");
    case "notes_pending": return i.resume_at ? t("st_notes_pending_until", { when: when(i.resume_at) }) : t("st_notes_pending");
    case "failed": return t("st_failed");
    default: return t("st_done");
  }
}
export const pillClass = (st) => ({ transcribing: "active", notes: "active", latex: "active", transcribed: "wait", notes_pending: "wait", failed: "bad", done: "ok" }[st] || "");

// Thin progress bar + the step names below it (done steps in text colour, the current one bold), as in the design
function latexProgressHtml(i) {
  const at = LATEX_STAGES.indexOf(i.stage);
  const steps = LATEX_STAGES.map((n, k) => `<span class="${i.status !== "latex" ? "" : k < at ? "done" : k === at ? "now" : ""}">${t("step_" + n)}</span>`);
  return `<div class="prog-bar" role="progressbar" aria-label="${t("progress")}">${i.status === "latex" ? `<span class="indet"></span>` : ""}</div>
    <div class="prog-steps">${steps.join("")}</div>`;
}

export function progressHtml(i) {
  if (i.kind === "latex") return latexProgressHtml(i);
  const current = currentStep(i);
  const pct = stepPct(i);
  const running = ["transcribing", "notes"].includes(i.status);
  const bar = pct != null ? `<span style="width:${pct}%"></span>` : running ? `<span class="indet"></span>` : "";
  const steps = STEP_NAMES.map((n, k) => {
    const cls = k === NOTES_STEP && i.notes === "never" ? "skip" : i.status === "queued" ? "" : k < current ? "done" : k === current ? "now" : "";
    return `<span class="${cls}">${t(n)}</span>`;
  }).join("");
  return `<div class="prog-bar" role="progressbar" ${pct != null ? `aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"` : ""}
    aria-label="${t("progress")}">${bar}</div><div class="prog-steps">${steps}</div>`;
}
