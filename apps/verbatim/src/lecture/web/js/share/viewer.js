// The page someone with a share link sees (served by the hub at /share/): the shared lectures per course, and per
// lecture the video with subtitles, notes and transcript, plus downloads. Read only; no access to Sequo.
// Addresses are …/share/#<code>, …/#<code>/vak/<id> and …/#<code>/les/<id>: the code stays in front, so whatever
// someone copies from the address bar is a working link. The code also becomes a cookie (for the video and track).
import { esc, fmtDate, fmtDayShort, fmtDuration, fmtTs, parseTs } from "../core/format.js";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const view = $("#view");
const API = "api";  // relative to /share/
const PART_RX = /\s*\b(?:deel|part)\s*\d+.*$/i;
let me = null, lectures = [], sel = "", lec = null, tab = "notes", loggedIn = "";

// "#abc/les/x" → { code: "abc", path: "/les/x" }; "#/les/x" (older links) → no code, the cookie decides
function parseHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  const i = h.indexOf("/");
  return { code: i < 0 ? h : h.slice(0, i), path: i < 0 ? "" : h.slice(i) };
}
const href = (path = "") => `#${encodeURIComponent(me?.code || loggedIn)}${path}`;

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("is-open");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-open"), 5000);
}

async function get(path) {
  const r = await fetch(`${API}/${path}`, { credentials: "same-origin" });
  if (r.status === 401) throw Object.assign(new Error("401"), { status: 401 });
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

async function start() {
  document.documentElement.lang = LANG;
  const { code, path } = parseHash();
  if (code && code !== loggedIn) {  // a (new) link: trade the code for a cookie
    const r = await fetch(`${API}/login`, { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ code }), credentials: "same-origin" });
    if (!r.ok) return noAccess(true);
    loggedIn = code;
  }
  try {
    [me, lectures] = await Promise.all([get("me"), get("lectures")]);
  } catch (e) {
    return e.status === 401 ? noAccess(false) : failed(e);
  }
  loggedIn = me.code || loggedIn;
  // an address without the code (older link, or "#/…"): put it back, so copying the address bar shares a working link
  $("#who").textContent = t("sh_for", { name: me.name });
  $(".share-brand").setAttribute("href", href());
  route();
}

window.addEventListener("hashchange", () => {
  const { code } = parseHash();
  if (code && code !== loggedIn) start();
  else if (me) route();
});

function noAccess(bad) {
  view.innerHTML = `<div class="empty share-empty"><h2>${t(bad ? "sh_bad_link" : "sh_need_link")}</h2><p>${t("sh_need_link_hint")}</p></div>`;
}
function failed(e) {
  view.innerHTML = `<div class="empty share-empty"><h2>${t("sh_offline")}</h2><p class="muted">${esc(e.message)}</p></div>`;
}

function route() {
  const { code, path } = parseHash();
  // an address without the code (older link, "#/…"): put it back, so copying the address bar shares a working link
  if (me?.code && code !== me.code) history.replaceState(null, "", location.pathname + location.search + href(path));
  const m = path.match(/^\/les\/(.+)$/);
  if (m) return renderLecture(m[1]);
  const c = path.match(/^\/vak\/(.+)$/);
  sel = c ? c[1] : "";
  renderLibrary();
}

// --- library: a block per course, lessons by number (newest first), parts of one lesson under one row -----------
const openGroups = new Set();

function groupParts(sorted) {
  const count = new Map();
  for (const l of sorted) if (l.group) count.set(l.group, (count.get(l.group) || 0) + 1);
  const out = [], seen = new Map();
  for (const l of sorted) {
    if (!l.group || count.get(l.group) < 2) { out.push(l); continue; }
    if (!seen.has(l.group)) { const g = { key: l.group, title: l.title.replace(PART_RX, ""), parts: [] }; seen.set(l.group, g); out.push(g); }
    seen.get(l.group).parts.push(l);
  }
  for (const g of seen.values()) g.parts.sort((a, b) => (a.part || 0) - (b.part || 0));
  return out;
}

const courseIndex = (id) => me.courses.findIndex((c) => c.id === id);
function lectureRow(l, part = false) {
  const title = part ? (l.title.match(PART_RX)?.[0].trim() || l.title).replace(/^./, (c) => c.toUpperCase()) : l.title;
  return `<li class="lecture${part ? " lecture-part" : ""}"><a class="row" href="${href(`/les/${encodeURIComponent(l.id)}`)}" data-course="${courseTone(l.course)}">
      <span class="dot"></span>
      <span class="row-main"><span class="row-title">${esc(title)}</span>
        <span class="sub">${esc(l.has_notes ? t("sh_with_notes") : t("sh_transcript"))}</span></span>
      <span class="row-trail">${esc(fmtDayShort(l.date))} · ${esc(fmtDuration(l.duration_s))}</span>
    </a></li>`;
}
function groupRow(g) {
  const open = openGroups.has(g.key);
  const total = g.parts.reduce((a, l) => a + (l.duration_s || 0), 0);
  return `<li class="lecture-group${open ? " is-open" : ""}" data-group="${esc(g.key)}"><div class="row" data-course="${courseTone(g.parts[0].course)}">
      <span class="dot"></span>
      <span class="row-main"><button class="row-title group-toggle" aria-expanded="${open}">${esc(g.title)}</button>
        <span class="sub">${esc(t("group_parts", { n: g.parts.length }))}</span></span>
      <span class="row-trail">${esc(fmtDayShort(g.parts[0].date))} · ${esc(fmtDuration(total))}
        <span class="group-chevron"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg></span></span>
    </div></li>` + (open ? g.parts.map((l) => lectureRow(l, true)).join("") : "");
}
// Course colours as in Verbatim: the palette order, one per shared course
const TONES = ["blue", "indigo", "purple", "pink", "red", "orange", "yellow", "green"];
const courseTone = (id) => me.courses.find((c) => c.id === id)?.color || TONES[Math.max(0, courseIndex(id)) % TONES.length];

function renderLibrary() {
  document.title = "Verbatim";
  lec = null;
  const shown = lectures.filter((l) => !sel || l.course === sel);
  const blocks = me.courses.filter((c) => !sel || c.id === sel).map((c) => ({
    ...c, items: groupParts(shown.filter((l) => l.course === c.id).sort((a, b) => (b.rank ?? 0) - (a.rank ?? 0))),
  })).filter((b) => b.items.length);
  const total = shown.reduce((a, l) => a + (l.duration_s || 0), 0);
  view.innerHTML = `
    <h1 class="large-title">${esc(sel ? me.courses.find((c) => c.id === sel)?.name || "" : t("nav_library"))}</h1>
    ${me.courses.length > 1 ? `<div class="chips share-chips"><a class="chip" href="${href()}" ${sel ? "" : 'aria-current="page"'}>${t("sh_all")}</a>
      ${me.courses.map((c) => `<a class="chip" href="${href(`/vak/${encodeURIComponent(c.id)}`)}" ${sel === c.id ? 'aria-current="page"' : ""}>${esc(c.name)}</a>`).join("")}</div>` : ""}
    <div class="hero"><span class="hero-number">${shown.length}</span>
      <span class="sub">${t(shown.length === 1 ? "lib_hero_1" : "lib_hero", { dur: fmtDuration(total) })}</span></div>
    ${blocks.length ? blocks.map((b) => `<section class="lib-block">
        ${sel ? "" : `<h2 class="group-title lib-course" data-course="${courseTone(b.id)}"><span class="dot"></span>${esc(b.name)}</h2>`}
        <ul class="list lectures">${b.items.map((it) => (it.parts ? groupRow(it) : lectureRow(it))).join("")}</ul>
      </section>`).join("") : `<div class="empty"><h2>${t("sh_none")}</h2><p>${t("sh_none_hint")}</p></div>`}`;
  $$(".lecture-group").forEach((r) => r.addEventListener("click", () => {
    if (openGroups.has(r.dataset.group)) openGroups.delete(r.dataset.group); else openGroups.add(r.dataset.group);
    const key = r.dataset.group;
    renderLibrary();
    $(`.lecture-group[data-group="${CSS.escape(key)}"] .group-toggle`)?.focus();
  }));
}

// --- one lecture -------------------------------------------------------------------------------------------
async function renderLecture(id) {
  view.innerHTML = `<div class="loading">${t("loading")}</div>`;
  try { lec = await get(`lectures/${encodeURIComponent(id)}`); }
  catch (e) { return e.status === 401 ? noAccess(false) : (view.innerHTML = `<div class="empty"><h2>${t("not_found")}</h2></div>`); }
  const s = lec.summary;
  const base = `${API}/lectures/${encodeURIComponent(id)}`;
  document.title = `${s.title} · ${s.course_name}`;
  tab = lec.notes ? "notes" : "transcript";
  const meta = [s.course_name, fmtDate(s.date), fmtDuration(s.duration_s)].filter(Boolean).join(" · ");
  view.innerHTML = `
    <a class="btn btn-plain share-back" href="${href(`/vak/${encodeURIComponent(s.course)}`)}">‹ ${esc(s.course_name)}</a>
    <div class="share-head"><h1 class="title">${esc(s.title)}</h1><p class="muted small">${esc(meta)}</p></div>
    <div class="lecture-layout">
      <aside class="stage">
        ${lec.has_video ? `<div class="player"><video id="player" controls preload="metadata" playsinline src="${base}/video">${
          lec.has_subtitles ? `<track kind="subtitles" label="${t("subtitles")}" srclang="${esc(lec.language || "nl")}" src="${base}/subtitles.vtt">` : ""}</video></div>`
          : `<div class="card flat" style="padding:16px"><p class="muted small">${t("sh_no_video")}</p></div>`}
        <div class="share-downloads">
          ${lec.has_video ? `<a class="btn btn-small" href="${base}/video?download=1" download>${t("sh_dl_video")}</a>` : ""}
          ${lec.has_subtitles ? `<a class="btn btn-small" href="${base}/subtitles.vtt?download=1" download>${t("sh_dl_subs")}</a>` : ""}
          <a class="btn btn-small" href="${base}/transcript.txt" download>${t("sh_dl_transcript")}</a>
        </div>
        ${lec.sections_detail.length ? `<div class="chapters card flat"><div class="chapters-head"><h4>${t("chapters")}</h4></div>
          ${lec.sections_detail.map((x) => `<button class="chapter" data-ts="${x.start}" data-part="${x.index}">
            <span class="t">${fmtTs(x.start)}</span><span>${esc(partTitle(x))}</span></button>`).join("")}</div>` : ""}
      </aside>
      <article class="card flat lec-doc">
        <div class="lec-tabs"><div class="segmented" id="tabs" role="group"></div></div>
        <div id="tab-body"></div>
      </article>
    </div>`;
  drawTabs();
  bindSubtitles();
}

function partTitle(x) {
  return lec.notes?.sections.find((n) => n.index === x.index)?.title || x.title || `${t("chapters")} ${x.index}`;
}

function drawTabs() {
  const tabs = [["notes", t("tab_notes")], ["transcript", t("tab_transcript")]];
  $("#tabs").innerHTML = tabs.map(([k, label]) => `<button type="button" aria-pressed="${tab === k}" data-tab="${k}">${label}</button>`).join("");
  $$("[data-tab]").forEach((b) => b.addEventListener("click", () => { tab = b.dataset.tab; drawTabs(); }));
  const body = $("#tab-body");
  if (tab === "notes") drawNotes(body); else drawTranscript(body);
}

const tsBtn = (x) => `<button class="ts" data-ts="${parseTs(x)}">${fmtTs(parseTs(x))}</button>`;
const tsSec = (s) => `<button class="ts" data-ts="${s}">${fmtTs(s)}</button>`;

function drawNotes(body) {
  const n = lec.notes;
  if (!n) { body.innerHTML = `<div class="empty"><h2>${t("no_notes")}</h2><p>${t("sh_no_notes_hint")}</p></div>`; return; }
  body.innerHTML = `<section class="summary"><h2 class="doc-label">${t("summary")}</h2>${n.summary.split(/\n\n+/).map((p) => `<p>${esc(p)}</p>`).join("")}</section>` +
    n.sections.map((x) => {
      const d = lec.sections_detail.find((y) => y.index === x.index);
      return `<section class="part" id="part-${x.index}">
      <div class="part-meta">${t("part_n", { n: x.index })}${d ? ` · ${tsSec(d.start)}–${fmtTs(d.end)}` : ""}</div>
      <h3 class="part-title">${esc(x.title)}</h3>
      ${x.slide_summary ? `<p class="on-slide"><b>${t("on_slide")}</b> ${esc(x.slide_summary)}</p>` : ""}
      ${x.lecturer_additions.length ? `<div class="block-label">${t("in_class")}</div><ul class="bullets">${x.lecturer_additions.map((p) => `<li>${esc(p.text)} ${tsBtn(p.ts)}</li>`).join("")}</ul>` : ""}
      ${x.definitions.length ? `<div class="block-label">${t("definitions")}</div><dl class="defs">${x.definitions.map((d2) => `<div><dt>${esc(d2.term)}</dt> — <dd>${esc(d2.definition)}</dd> ${tsBtn(d2.ts)}</div>`).join("")}</dl>` : ""}
      ${x.examples.length ? `<div class="block-label">${t("examples")}</div><ul class="bullets">${x.examples.map((p) => `<li>${esc(p.text)} ${tsBtn(p.ts)}</li>`).join("")}</ul>` : ""}
      ${(x.exam_hints || []).map((h) => `<div class="hint"><div><b>${t("exam_hint")}:</b> “${esc(h.quote)}” ${tsBtn(h.ts)}</div></div>`).join("")}
    </section>`;
    }).join("");
}

function drawTranscript(body) {
  const secs = lec.sections_detail.length ? lec.sections_detail : [{ index: 1, title: "", start: 0, end: 1e9 }];
  body.innerHTML = `<div class="tr-tools"><input type="search" id="tr-q" placeholder="${t("search_transcript")}" aria-label="${t("search_transcript")}"><span class="muted small" id="tr-count"></span></div><div id="tr-body"></div>`;
  const draw = (q) => {
    const rx = q ? new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i") : null;
    let hits = 0;
    $("#tr-body").innerHTML = secs.map((x) => {
      const lines = lec.segments.filter((g) => g.start >= x.start && g.start < x.end && (!rx || rx.test(g.text)));
      hits += rx ? lines.length : 0;
      if (!lines.length) return "";
      return `<section class="tr-part" id="tr-${x.index}"><h3>${x.index}. ${esc(partTitle(x))}</h3>${lines.map((g) => {
        let text = esc(g.text);
        if (rx) text = text.replace(new RegExp(esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), (m) => `<mark>${m}</mark>`);
        return `<div class="tr-line" data-start="${g.start}">${tsSec(g.start)}<span>${text}</span></div>`;
      }).join("")}</section>`;
    }).join("") || `<p class="muted">${t("no_match")}</p>`;
    $("#tr-count").textContent = rx ? t("lines_n", { n: hits }) : "";
  };
  draw("");
  $("#tr-q").addEventListener("input", (e) => draw(e.target.value.trim()));
}

// timestamps and transcript lines seek the video
view.addEventListener("click", (e) => {
  const line = e.target.closest(".tr-line");
  const b = e.target.closest("[data-ts]") || (line && !String(getSelection()).trim() ? line.querySelector("[data-ts]") : null);
  const player = $("#player");
  if (!b || !player) return;
  const time = Number(b.dataset.ts);
  player.currentTime = time;
  player.play().catch(() => {});
  if (b.dataset.part) ($(`#part-${b.dataset.part}`) || $(`#tr-${b.dataset.part}`))?.scrollIntoView({ behavior: "smooth", block: "start" });
});

// Subtitles: "c" or the player's own menu, remembered as in Verbatim
let subsOn = (() => { try { return localStorage.getItem("lt-subs") === "1"; } catch { return false; } })();
function bindSubtitles() {
  const track = $("#player")?.textTracks[0];
  if (track) track.mode = subsOn ? "showing" : "hidden";
}
document.addEventListener("keydown", (e) => {
  if (e.key !== "c" || e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, textarea")) return;
  const track = $("#player")?.textTracks[0];
  if (!track) return;
  subsOn = track.mode !== "showing";
  track.mode = subsOn ? "showing" : "hidden";
  try { localStorage.setItem("lt-subs", subsOn ? "1" : "0"); } catch { /* private window */ }
  toast(t(subsOn ? "subtitles_on" : "subtitles_off"));
});

// Lectures you add show up without reloading: the list is fetched again every minute (and when the tab comes
// back into view); a lecture whose video is still on its way checks every 30 s.
async function refreshList() {
  if (!me || lec || document.hidden) return;
  try {
    const [who, fresh] = await Promise.all([get("me"), get("lectures")]);  // courses on the link may change too
    if (JSON.stringify([who, fresh]) !== JSON.stringify([me, lectures])) { me = who; lectures = fresh; renderLibrary(); }
  } catch { /* offline for a moment: try again next round */ }
}
async function refreshLecture() {
  if (!lec || lec.has_video || document.hidden) return;
  try {
    const fresh = await get(`lectures/${encodeURIComponent(lec.summary.id)}`);
    if (fresh.has_video) renderLecture(lec.summary.id);
  } catch { /* try again */ }
}
setInterval(refreshList, 60000);
setInterval(refreshLecture, 30000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) { refreshList(); refreshLecture(); } });

start();
