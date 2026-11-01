import "@studie/design/tokens.css";
import "@studie/design/components.css";
import { icon } from "@studie/design/icons.js";
import { registerSW } from "virtual:pwa-register";
import { toBackup } from "./domain/backup.js";
import { toNotes } from "./domain/notes.js";
import { isOpen, summarize } from "./domain/sessions.js";
import * as store from "./db/store.js";
import { lang, setLang, setTheme, t } from "./i18n/index.js";
import { renderCourse, courseView } from "./screens/course.js";
import { renderOverview, view } from "./screens/overview.js";
import { renderSettings, syncStatusText } from "./screens/settings.js";
import { connect, nudge, startSync } from "./sync/index.js";
import { startSwiftSkip } from "./sync/swiftskip.js";
import * as sheets from "./screens/sheets.js";
import { $, $$, download, esc } from "./ui/dom.js";
import { initSheet, toast } from "./ui/feedback.js";
import { captureRects, playFlip, playHero } from "./ui/flip.js";
import { clickIgnored, initGestures } from "./ui/gestures.js";
import { initChart, initShortcuts } from "./ui/shortcuts.js";
import { numbersNow, sessionLabel } from "./ui/rows.js";

const { state } = store;
const app = $("#app");
app.innerHTML = `<div id="stage">
  <div id="shell" class="split">
    <div class="topbar" aria-hidden="true"></div>
    <aside class="sidebar" id="sidebar"></aside>
    <div id="view" class="view"></div>
    <nav class="tabbar" id="tabbar"></nav>
    <button class="fab" id="fab" data-action="add"></button>
  </div>
  <div id="sheet-root">
    <div class="scrim" id="scrim"></div>
    <div class="sheet" id="sheet" role="dialog" aria-modal="true" tabindex="-1"></div>
  </div>
  <div class="toast" id="toast" role="status"></div>
</div>`;

const route = () => {
  const [, page, id] = location.hash.split("/");
  return { page: page || "", id };
};

function renderChrome() {
  const { page, id } = route();
  const tabs = [["", "overview", "overview"], ["instellingen", "settings", "settings"]];
  $("#tabbar").setAttribute("aria-label", t("overview"));
  $("#tabbar").dataset.active = page === "instellingen" ? "1" : "0";
  if (!$("#tabbar").childElementCount || $("#tabbar").dataset.lang !== lang()) {
    $("#tabbar").dataset.lang = lang();
    $("#tabbar").innerHTML = tabs.map(([path, name, key]) =>
    `<a class="tab" href="#/${path}" ${(path === page || (page === "vak" && !path)) ? 'aria-current="page"' : ""}>${icon(name)}<span>${esc(t(key))}</span></a>`).join("");
  }
  $$(".tab").forEach((tab, i) => { if (i === +$("#tabbar").dataset.active) tab.setAttribute("aria-current", "page"); else tab.removeAttribute("aria-current"); });

  const summary = state.semester ? summarize(state.courses, state.sessions, new Date()) : null;
  $("#sidebar").setAttribute("aria-label", t("courses"));
  $("#sidebar").innerHTML = `
    <div class="side-brand"><img class="side-logo" src="./icon.svg" alt="" width="28" height="28"><span>Inhaal</span></div>
    ${state.semester ? `<button class="btn btn-primary btn-block side-add" data-action="add">${icon("plus")}${esc(t("add"))}</button>` : ""}
    <ul class="list list-side">
      <li><a class="row" href="#/" ${page === "" ? 'aria-current="page"' : ""}>${icon("overview")}<span class="row-main"><span>${esc(t("overview"))}</span></span>${summary ? `<span class="count">${summary.open}</span>` : ""}</a></li>
    </ul>
    ${summary ? `<p class="group-title side-title">${esc(t("courses"))}</p>
    <ul class="list list-side">${summary.perCourse.map((p) => `<li><a class="row" href="#/vak/${esc(p.course.id)}" data-course="${esc(p.course.colorKey)}" ${id === p.course.id ? 'aria-current="page"' : ""}>
      <span class="dot"></span><span class="row-main"><span>${esc(p.course.name)}</span></span>${p.open ? `<span class="count">${p.open}</span>` : ""}</a></li>`).join("")}</ul>` : ""}
    <ul class="list list-side side-end">
      <li><a class="row" href="#/instellingen" ${page === "instellingen" ? 'aria-current="page"' : ""}>${icon("settings")}<span class="row-main"><span>${esc(t("settings"))}</span></span></a></li>
    </ul>`;

  const fab = $("#fab");
  fab.innerHTML = icon("plus");
  fab.setAttribute("aria-label", t("add"));
  fab.hidden = !state.semester || page === "instellingen";
}

// Staat als gewone rij bovenaan de pagina, zodat ze de inhoud opschuift in plaats van erover te liggen.
let updateReady = false;
let updateApp = () => {};

function render(quiet = false) {
  const now = new Date();
  const { page, id } = route();
  const root = $("#view");
  if (page === "vak") renderCourse(root, id, now);
  else if (page === "instellingen") renderSettings(root);
  else renderOverview(root, now);
  if (updateReady) $("#view .page")?.insertAdjacentHTML("afterbegin", `<div class="banner"><span>${esc(t("newVersion"))}</span>
    <button class="btn btn-small btn-plain" data-action="update-app">${esc(t("refresh"))}</button></div>`);
  renderChrome();
  playHero(!quiet);
}

async function refresh({ flip = true, quiet = false } = {}) {
  const before = flip ? captureRects() : null;
  render(quiet);
  if (before) playFlip(before);
  nudge();
}

sheets.setRefresh(refresh);

// Afvinken is direct: het scherm verandert meteen en opslaan gebeurt erachter. Zo raakt elke tik de volgende les.
let batch = new Map();
let batchAt = 0;

function tick(id) {
  const session = store.sessionById(id);
  const open = isOpen(session, new Date());
  const label = sessionLabel(session, numbersNow());
  const saved = store.setStatus([id], open ? "watched" : "upcoming");
  navigator.vibrate?.(10);
  refresh({ flip: false, quiet: true });

  const time = performance.now();
  if (time - batchAt > 5000) batch = new Map();
  batchAt = time;
  if (!open) { batch.delete(id); return; }
  batch.set(id, saved);
  const undoAll = [...batch.values()];
  toast(batch.size > 1 ? t("tickedMany", { n: batch.size }) : t("ticked", { label }), async () => {
    batch = new Map();
    await Promise.all(undoAll.map(async (pending) => (await pending)()));
    refresh({ flip: false, quiet: true });
  });
}

async function exportJson() {
  const data = await store.dumpAll();
  const now = new Date();
  download(`inhaal-${now.toISOString().slice(0, 10)}.json`, JSON.stringify(toBackup(data, now), null, 2), "application/json");
  await store.markBackup();
  render();
}

function exportNotes() {
  const text = toNotes(state.courses, state.sessions, new Date());
  navigator.clipboard?.writeText(text).then(() => toast(t("copied"))).catch(() => {});
  download("inhaal-notes.txt", text, "text/plain");
}

const actions = {
  "sync-connect": async () => {
    await connect($("#sync-code").value);
    render();
  },
  upload: sheets.uploadRooster,
  add: sheets.openAdd,
  notes: sheets.openNotes,
  erase: sheets.openErase,
  "export-json": exportJson,
  "export-notes": exportNotes,
  "import-json": sheets.restoreBackup,
  "link-recordings": sheets.openLinkRecording,
  "update-app": () => updateApp(true),
  "dismiss-install": async () => { await store.dismiss("installDismissed"); render(); },
  "dismiss-weeks": async () => { await store.dismiss("weeksDismissed"); render(); },
  select: () => { courseView.selecting = new Set(); render(); },
  "select-cancel": () => { courseView.selecting = null; render(); },
  "tick-selected": async () => {
    const ids = [...courseView.selecting];
    const undo = await store.setStatus(ids, "watched");
    courseView.selecting = null;
    refresh();
    toast(t("tickedMany", { n: ids.length }), async () => { await undo(); refresh(); });
  },
};

document.addEventListener("click", (e) => {
  if (clickIgnored()) {
    e.preventDefault();
    return;
  }
  const target = e.target.closest("[data-action],[data-tick],[data-pick],[data-options],[data-view],[data-filter],[data-edit-course],[data-lang],[data-theme-choice],[data-speed]");
  if (!target || target.closest("#sheet")) return;
  const { action, tick: tickId, pick, options, view: viewChoice, filter, editCourse, lang: choice, themeChoice, speed } = target.dataset;
  if (action) actions[action]();
  else if (tickId) tick(tickId);
  else if (pick) {
    if (courseView.selecting.has(pick)) courseView.selecting.delete(pick); else courseView.selecting.add(pick);
    render();
  } else if (options) { if (!courseView.selecting) sheets.openOptions(options); }
  else if (viewChoice) {
    const [key, value] = viewChoice.split(":");
    if (key === t("type")) view.filter = value; else view.mode = value;
    refresh({ flip: false });
  } else if (filter) { courseView.filter = filter; refresh({ flip: false }); }
  else if (editCourse) sheets.openCourse(editCourse);
  else if (choice) { setLang(choice); render(); }
  else if (themeChoice) { setTheme(themeChoice); render(); }
  else if (speed) store.updateSemester({ playbackSpeed: +speed }).then(() => refresh({ flip: false, quiet: true }));
});

document.addEventListener("change", async (e) => {
  const { semester, duration } = e.target.dataset;
  if (semester && e.target.value) { await store.updateSemester({ [semester]: e.target.value }); render(); }
  if (duration && +e.target.value > 0) { await store.setAllDurations({ [duration]: +e.target.value }); render(); }
});

window.addEventListener("hashchange", () => {
  courseView.selecting = null;
  courseView.filter = "all";
  window.scrollTo(0, 0);
  $("#view").scrollTo(0, 0);
  render();
  $("#view .page")?.classList.add("page-enter");
});

// Na het einduur schuift een les vanzelf naar "in te halen", ook als de app openstaat.
document.addEventListener("visibilitychange", () => { if (!document.hidden) render(); });

initSheet();
initChart($("#view"));
initShortcuts({
  onAdd: sheets.openAdd,
  onCourse: (index) => {
    const course = summarize(state.courses, state.sessions, new Date()).perCourse[index]?.course;
    if (course) location.hash = `#/vak/${course.id}`;
  },
});
initGestures($("#view"), { onTick: tick, onOptions: sheets.openOptions });
document.documentElement.lang = lang();
await store.load();
render();

startSync({
  onChange: () => { if (!$("#sheet-root").classList.contains("is-open")) refresh(); },
  onRooster: ({ added, updated, vanished }) => {
    refresh();
    if (added || updated) toast(t("roosterChanged", { added, updated }));
    if (vanished.length) sheets.openVanished(vanished);
  },
  onStatus: () => {
    const status = $("#sync-status");
    if (status) status.textContent = syncStatusText();
    if (route().page === "instellingen" && !status) render();
  },
});

startSwiftSkip({
  onLinked: () => { if (route().page === "instellingen") render(); },
  onResult: ({ ticked, undo }) => {
    if (!$("#sheet-root").classList.contains("is-open")) refresh();
    if (!ticked.length) return;
    const message = ticked.length > 1 ? t("tickedRecordings", { n: ticked.length })
      : t("tickedRecording", { label: sessionLabel(store.sessionById(ticked[0]), numbersNow()) });
    toast(message, async () => { await undo(); refresh(); });
  },
});

updateApp = registerSW({
  onNeedRefresh() {
    updateReady = true;
    render(true);
  },
});
