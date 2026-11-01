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
import { renderSettings } from "./screens/settings.js";
import * as sheets from "./screens/sheets.js";
import { $, download, esc } from "./ui/dom.js";
import { initSheet, toast } from "./ui/feedback.js";
import { captureRects, playFlip } from "./ui/flip.js";
import { clickIgnored, initGestures } from "./ui/gestures.js";
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
  <div class="update-banner" id="update" hidden></div>
</div>`;

// Op het beginscherm van een iPhone is het venster korter dan het scherm; de echte hoogte komt van screen.
function fitScreen() {
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  if (!standalone || !/iphone/i.test(navigator.userAgent)) return;
  const height = window.innerWidth < window.innerHeight ? screen.height : screen.width;
  document.documentElement.style.setProperty("--app-height", `${height}px`);
}
fitScreen();
window.addEventListener("resize", fitScreen);

const route = () => {
  const [, page, id] = location.hash.split("/");
  return { page: page || "", id };
};

function renderChrome() {
  const { page, id } = route();
  const tabs = [["", "overview", "overview"], ["instellingen", "settings", "settings"]];
  $("#tabbar").setAttribute("aria-label", t("overview"));
  $("#tabbar").innerHTML = tabs.map(([path, name, key]) =>
    `<a class="tab" href="#/${path}" ${(path === page || (page === "vak" && !path)) ? 'aria-current="page"' : ""}>${icon(name)}<span>${esc(t(key))}</span></a>`).join("");

  const summary = state.semester ? summarize(state.courses, state.sessions, new Date()) : null;
  $("#sidebar").setAttribute("aria-label", t("courses"));
  $("#sidebar").innerHTML = `
    <div class="side-brand"><span>Inhaal</span></div>
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

function render() {
  const now = new Date();
  const { page, id } = route();
  const root = $("#view");
  if (page === "vak") renderCourse(root, id, now);
  else if (page === "instellingen") renderSettings(root);
  else renderOverview(root, now);
  renderChrome();
}

async function refresh({ flip = true } = {}) {
  const before = flip ? captureRects() : null;
  render();
  if (before) playFlip(before);
}

sheets.setRefresh(refresh);

// Afgevinkte rijen blijven staan tot je even stopt, zodat de lijst niet onder je duim verschuift.
const SETTLE_MS = 2500;
let settle = null;
let batch = [];

function settleLater(ms = SETTLE_MS) {
  clearTimeout(settle);
  settle = setTimeout(() => { settle = null; refresh(); }, ms);
}

async function tick(id, target) {
  const session = store.sessionById(id);
  const open = isOpen(session, new Date());
  const label = sessionLabel(session, numbersNow());
  const undo = await store.setStatus([id], open ? "watched" : "upcoming");
  document.querySelectorAll(`.check[data-tick="${CSS.escape(id)}"]`).forEach((c) => c.setAttribute("aria-checked", open));
  navigator.vibrate?.(10);
  renderChrome();
  // De kaart Volgende toont meteen de volgende les; in een lijst wachten we op de pauze.
  settleLater(target?.closest(".check") ? SETTLE_MS : 0);
  if (!open) return;
  batch = settle && batch.length && performance.now() - batch.at(-1).at < 5000 ? batch : [];
  batch.push({ undo, at: performance.now() });
  const undoAll = batch;
  toast(batch.length > 1 ? t("tickedMany", { n: batch.length }) : t("ticked", { label }), async () => {
    clearTimeout(settle);
    settle = null;
    batch = [];
    await Promise.all(undoAll.map((item) => item.undo()));
    refresh();
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
  upload: sheets.uploadRooster,
  add: sheets.openAdd,
  notes: sheets.openNotes,
  erase: sheets.openErase,
  "export-json": exportJson,
  "export-notes": exportNotes,
  "import-json": sheets.restoreBackup,
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
  const target = e.target.closest("[data-action],[data-tick],[data-pick],[data-options],[data-view],[data-filter],[data-edit-course],[data-lang],[data-theme-choice]");
  if (!target || target.closest("#sheet")) return;
  const { action, tick: tickId, pick, options, view: viewChoice, filter, editCourse, lang: choice, themeChoice } = target.dataset;
  if (action) actions[action]();
  else if (tickId) tick(tickId, e.target);
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
});

document.addEventListener("toggle", (e) => {
  if (e.target.matches?.(".finished")) courseView.finishedOpen = e.target.open;
}, true);

document.addEventListener("change", async (e) => {
  const { semester, duration } = e.target.dataset;
  if (semester && e.target.value) { await store.updateSemester({ [semester]: e.target.value }); render(); }
  if (duration && +e.target.value > 0) { await store.setAllDurations({ [duration]: +e.target.value }); render(); }
});

window.addEventListener("hashchange", () => {
  courseView.selecting = null;
  courseView.filter = "all";
  courseView.finishedOpen = false;
  $("#view").scrollTo(0, 0);
  render();
});

// Na het einduur schuift een les vanzelf naar "in te halen", ook als de app openstaat.
document.addEventListener("visibilitychange", () => { if (!document.hidden) render(); });

initSheet();
initGestures($("#view"), { onTick: tick, onOptions: sheets.openOptions });
document.documentElement.lang = lang();
await store.load();
render();

// Een aanraking in de lijst stelt het opschuiven uit: je bent nog bezig.
$("#view").addEventListener("pointerdown", () => { if (settle) settleLater(); });

const updateSW = registerSW({
  onNeedRefresh() {
    const banner = $("#update");
    banner.hidden = false;
    banner.innerHTML = `<div class="banner"><span>${esc(t("newVersion"))}</span><button class="btn btn-small btn-plain">${esc(t("refresh"))}</button></div>`;
    banner.querySelector("button").addEventListener("click", () => updateSW(true));
  },
});
