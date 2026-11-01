// Lecture page: big video + parts on the left, notes / transcript / … tabs on the right.
import { api, post } from "../core/api.js";
import { $, $$, view } from "../core/dom.js";
import { esc, fmtDate, fmtLong, fmtTs, parseTs } from "../core/format.js";
import { ICON } from "../core/icons.js";
import { S } from "../core/state.js";
import { closeMenus, inlineEdit, poll, setBarTitle, toast } from "../core/ui.js";
import { deleteLecture, renameLecture } from "../shared/actions.js";

let lec = null, lecTab = "notes", follow = true;

export async function renderLecture(id, tab) {
  view.innerHTML = `<div class="loading">${t("loading")}</div>`;
  try { lec = await api(`/api/lectures/${encodeURIComponent(id)}`); }
  catch (e) { view.innerHTML = `<div class="empty"><h2>${t("not_found")}</h2><p>${esc(e.message)}</p></div>`; return; }
  if (!S.courses.length) S.courses = await api("/api/courses").catch(() => []);
  lecTab = tab || (lec.notes ? "notes" : "transcript");
  const meta = [fmtDate(lec.date), lec.duration_s ? fmtLong(lec.duration_s) : "", lec.sections ? t("sections_n", { n: lec.sections }) : ""].filter(Boolean);
  const canNotes = ["transcribed", "done", "failed", "notes_pending"].includes(lec.status);
  // actions + path live in the slim top bar (index.html .pagebar); the router clears them on every page change
  $("#bar-actions").innerHTML = `
    ${canNotes ? `<button class="btn ${lec.notes ? "" : "primary"}" id="make-notes">${lec.notes ? t("remake_notes") : t("make_notes")}</button>` : ""}
    ${lec.files.includes("flashcards_anki.csv") ? `<a class="btn" href="/api/lectures/${encodeURIComponent(lec.id)}/files/flashcards_anki.csv">${t("anki")}</a>` : ""}
    <button class="btn" id="open-folder">${t("files")}</button>
    <button class="btn ghost danger" id="delete-lecture">${t("delete")}</button>`;
  setBarTitle(`${lec.course_name} / ${lec.title}`, true);
  view.innerHTML = `
    <div class="lecture-layout fade-in">
      <aside class="stage">
        <div class="lec-head">
          <h1 class="editable" id="lec-title" title="${t("rename")}">${esc(lec.title)}</h1>
          <p class="muted">${meta.map(esc).join(" · ")}</p>
          <p class="made-with">${[lec.models.stt ? `${t("transcript_by")}: ${esc(lec.models.stt)}` : "",
            lec.models.notes ? `${t("notes_by")}: ${esc(lec.models.notes)}` : ""].filter(Boolean).join(" · ")}</p>
        </div>
        ${lec.media_available ? `<div class="player"><video id="player" controls preload="auto" src="/api/lectures/${encodeURIComponent(lec.id)}/media"></video></div>`
          : lec.media_on_mac ? `<div class="panel on-mac"><p>${t("lec_on_mac")}</p><button class="btn" id="restore-media">${t("lec_restore")}</button></div>`
          : `<div class="panel" style="padding:16px"><p class="muted small">${t("no_video")}</p></div>`}
        <div class="chapters" id="chapters"></div>
      </aside>
      <article class="panel lec-doc">
        <div class="tabs" id="tabs" role="tablist"></div>
        <div id="tab-body"></div>
      </article>
    </div>`;
  $("#open-folder").addEventListener("click", () => post(`/api/lectures/${encodeURIComponent(lec.id)}/open-folder`).catch((e) => toast(e.message, true)));
  $("#lec-title").addEventListener("click", (e) => inlineEdit(e.currentTarget, lec.title, async (title) => {
    await renameLecture(lec.id, title);
    lec.title = title;
    e.target.textContent = title;
  }, "", () => setBarTitle(`${lec.course_name} / ${lec.title}`, true)));
  $("#delete-lecture").addEventListener("click", async () => { if (await deleteLecture(lec.id, lec.title)) location.hash = "#/"; });
  $("#make-notes")?.addEventListener("click", async () => {
    try {
      const r = await post(`/api/lectures/${encodeURIComponent(lec.id)}/notes`);
      toast(r.worker ? t("notes_queued") : t("notes_queued_noworker"));
    } catch (e) { toast(e.message, true); }
  });
  $("#restore-media")?.addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    e.currentTarget.textContent = "…";
    try { await post("/api/archive/restore", { jobs: [lec.id] }); } catch (err) { toast(err.message, true); return; }
    poll(async () => {  // until the copy is back, then reload the page with the video
      const p = await api("/api/archive/progress").catch(() => null);
      if (p && !p.running) { if (p.error) toast(p.error, true); renderLecture(id, lecTab); }
    }, 2000);
  });
  drawChapters();
  drawTabs();
  lines = null;
  $("#player")?.addEventListener("timeupdate", (e) => syncToTime(e.target.currentTime));
  if (["queued", "transcribing", "notes", "transcribed", "notes_pending"].includes(lec.status)) {
    poll(async () => {
      const fresh = await api(`/api/lectures/${encodeURIComponent(id)}`).catch(() => null);
      if (fresh && (fresh.status !== lec.status || !!fresh.notes !== !!lec.notes)) renderLecture(id, lecTab);
    }, 5000);
  }
}

function partTitle(s) {
  return lec.notes?.sections.find((n) => n.index === s.index)?.title || s.title || `${t("chapters")} ${s.index}`;
}
function drawChapters() {
  const secs = lec.sections_detail;
  $("#chapters").innerHTML = `
    <div class="chapters-head"><h4>${t("chapters")}</h4>
      ${lec.media_available ? `<label><input type="checkbox" class="switch" id="follow" ${follow ? "checked" : ""}>${t("follow")}</label>` : ""}</div>` +
    secs.map((s) => `<button class="chapter" data-ts="${s.start}" data-part="${s.index}">
      <span class="t">${fmtTs(s.start)}</span><span>${esc(partTitle(s))}</span></button>`).join("");
  $("#follow")?.addEventListener("change", (e) => { follow = e.target.checked; });
}

// Kept light on purpose: it runs ~4×/s while the video plays, and heavy page work (searching ~1500
// transcript lines, smooth-scrolling the whole page) made the image lag behind the sound in Zen/Firefox.
let lastPart = -1, lastLine = null, lines = null, lineStarts = null;
function indexLines() {  // transcript lines + their start times, rebuilt when the transcript tab is drawn
  lines = $$(".tr-line");
  lineStarts = lines.map((l) => Number(l.dataset.start));
  lastLine = null;
}
function lineAt(time) {  // last line starting at or before `time` (binary search)
  let lo = 0, hi = lineStarts.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (lineStarts[mid] <= time) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found >= 0 ? lines[found] : null;
}
function syncToTime(time) {
  const secs = lec.sections_detail;
  if (lines && lines.length && lines[0].isConnected) {
    const line = lineAt(time);
    if (line !== lastLine) {
      lastLine?.classList.remove("now");
      line?.classList.add("now");
      lastLine = line;
    }
  }
  const idx = secs.findIndex((s) => time >= s.start && time < s.end);
  if (idx === lastPart) return;
  const first = lastPart === -1;
  // no scrolling on the very first update (pressing play at 0:00 jumped the page), never smooth, and not
  // right after the user clicked a time: they are where they want to be (see the click handler below)
  showPart(idx, follow && !first && performance.now() > quietUntil);
}
let quietUntil = 0;
function showPart(idx, scroll) {
  lastPart = idx;
  const part = lec.sections_detail[idx]?.index;
  $$(".chapter").forEach((b) => b.classList.toggle("now", Number(b.dataset.part) === part));
  $$(".part").forEach((p) => p.classList.toggle("now", Number(p.dataset.part) === part));
  if (scroll && part != null) {
    $(`.chapter[data-part="${part}"]`)?.scrollIntoView({ block: "nearest" });
    ($(`#part-${part}`) || $(`#tr-${part}`))?.scrollIntoView({ block: "start" });
  }
}

// Jump, wait until the browser has the picture at the new time ("seeked"), then play. Calling play() right
// after setting currentTime made Zen/Firefox start the sound while the picture was still being decoded from
// the previous keyframe (up to 10 s of video in some recordings): the image froze, then lagged behind.
function seekAndPlay(player, time) {
  const play = () => player.play().catch(() => {});
  if (Math.abs(player.currentTime - time) < 0.3) return play();
  player.pause();
  player.addEventListener("seeked", play, { once: true });
  player.currentTime = time;
}

// timestamps anywhere on the page seek the video (registered once, on #view)
view.addEventListener("click", (e) => {
  // A whole transcript line works like its timestamp, unless the user is selecting text (that opens the fix box).
  const line = e.target.closest(".tr-line");
  const inLine = line && !e.target.closest("button, a, input") && !String(getSelection()).trim();
  const b = e.target.closest("[data-ts]") || (inLine ? line.querySelector("[data-ts]") : null);
  if (!b) return;
  const player = $("#player");
  const time = Number(b.dataset.ts);
  // Mark the new part now, without scrolling, and keep "follow" from scrolling while the seek settles: it used
  // to pull the page to the top of the part (away from the clicked line), and during the seek the player
  // briefly reports the old time, which jumped the page back and forth.
  if (lec?.sections_detail) showPart(lec.sections_detail.findIndex((s) => time >= s.start && time < s.end), false);
  quietUntil = performance.now() + 1500;
  if (player) seekAndPlay(player, time);
  if (b.dataset.part) ($(`#part-${b.dataset.part}`) || $(`#tr-${b.dataset.part}`))?.scrollIntoView({ behavior: "smooth", block: "start" });
});

function drawTabs() {
  const n = lec.notes;
  const hints = n ? n.sections.reduce((a, s) => a + (s.exam_hints?.length || 0), 0) : 0;
  const tabs = [["notes", "tab_notes", null], ["transcript", "tab_transcript", null]];
  if (hints) tabs.push(["hints", "tab_hints", hints]);
  if (n?.quiz?.length) tabs.push(["quiz", "tab_quiz", n.quiz.length]);
  if (n?.flashcards?.length) tabs.push(["cards", "tab_cards", n.flashcards.length]);
  if (n?.glossary?.length) tabs.push(["glossary", "tab_glossary", n.glossary.length]);
  if (lec.terms.length || lec.fixes.length) tabs.push(["terms", "tab_terms", lec.terms.length]);
  if (lec.termfix || lec.segments.length) tabs.push(["suggest", "tab_suggest", (lec.termfix?.suggestions || []).filter((x) => x.status === "open").length]);
  tabs.push(["review", "tab_review", null]);
  if (!tabs.some(([id]) => id === lecTab)) lecTab = "notes";
  $("#tabs").innerHTML = tabs.map(([id, key, count]) => `<button data-tab="${id}" class="${lecTab === id ? "on" : ""}">${t(key)}${count ? `<span class="count">${count}</span>` : ""}</button>`).join("");
  $$("#tabs button").forEach((b) => b.addEventListener("click", () => {
    lecTab = b.dataset.tab;
    history.replaceState(null, "", `#/lecture/${encodeURIComponent(lec.id)}/${lecTab}`);
    drawTabs();
  }));
  const body = $("#tab-body");
  body.innerHTML = "";
  body.className = "fade-in";
  ({ notes: drawNotes, transcript: drawTranscript, hints: drawHints, quiz: drawQuiz, cards: drawCards, glossary: drawGlossary, terms: drawTerms, suggest: drawSuggest, review: drawReview })[lecTab](body);
  lastPart = -1;
}

const tsBtn = (x) => `<button class="ts" data-ts="${parseTs(x)}">${fmtTs(parseTs(x))}</button>`;
const tsSec = (s) => `<button class="ts" data-ts="${s}">${fmtTs(s)}</button>`;

function noNotes(body) {
  const coming = ["transcribed", "notes", "notes_pending"].includes(lec.status);
  body.innerHTML = `<div class="empty"><h2>${coming ? t("notes_coming") : t("no_notes")}</h2>
    <p>${coming ? t("notes_coming_hint") : t("no_notes_hint")}</p>
    ${lec.files.includes("study_pack.md") && !coming ? `<a class="btn" href="/api/lectures/${encodeURIComponent(lec.id)}/files/study_pack.md">${t("study_pack")}</a>` : ""}</div>`;
}
function partMeta(index) {  // "Part 2 · slide 57 · 3:07–4:14" above each part's heading
  const d = lec.sections_detail.find((x) => x.index === index);
  if (!d) return `<div class="part-meta">${t("part_n", { n: index })}</div>`;
  const pages = [...new Set(d.slides.map((p) => p.page))];
  const slide = pages.length ? t("slide_n", { n: pages[0] + (pages.length > 1 ? "–" + pages[pages.length - 1] : "") }) : "";
  return `<div class="part-meta">${[t("part_n", { n: index }), slide].filter(Boolean).join(" · ")} · <span>${tsSec(d.start)}–${fmtTs(d.end)}</span>
    ${d.low_confidence ? `<span class="uncertain">${t("uncertain")}</span>` : ""}</div>`;
}
function drawNotes(body) {
  const n = lec.notes;
  if (!n) return noNotes(body);
  body.innerHTML = `<section class="summary"><h2 class="doc-label">${t("summary")}</h2>${n.summary.split(/\n\n+/).map((p) => `<p>${esc(p)}</p>`).join("")}</section>` +
    n.sections.map((s) => `
    <section class="part" id="part-${s.index}" data-part="${s.index}">
      ${partMeta(s.index)}
      <h3 class="part-title">${esc(s.title)}</h3>
      ${s.slide_summary ? `<p class="on-slide"><b>${t("on_slide")}</b> ${esc(s.slide_summary)}</p>` : ""}
      ${s.lecturer_additions.length ? `<div class="block-label">${t("in_class")}</div><ul class="bullets">${s.lecturer_additions.map((p) => `<li>${esc(p.text)} ${tsBtn(p.ts)}</li>`).join("")}</ul>` : ""}
      ${s.definitions.length ? `<div class="block-label">${t("definitions")}</div><dl class="defs">${s.definitions.map((d) => `<div><dt>${esc(d.term)}</dt> — <dd>${esc(d.definition)}</dd> ${tsBtn(d.ts)}</div>`).join("")}</dl>` : ""}
      ${s.examples.length ? `<div class="block-label">${t("examples")}</div><ul class="bullets">${s.examples.map((p) => `<li>${esc(p.text)} ${tsBtn(p.ts)}</li>`).join("")}</ul>` : ""}
      ${(s.exam_hints || []).map((h) => `<div class="hint"><div><b>${t("exam_hint")}:</b> “${esc(h.quote)}” ${tsBtn(h.ts)}</div></div>`).join("")}
    </section>`).join("");
}
function drawTranscript(body) {
  const secs = lec.sections_detail.length ? lec.sections_detail : [{ index: 1, title: "", start: 0, end: 1e9 }];
  body.innerHTML = `<div class="tr-tools"><input type="search" id="tr-q" placeholder="${t("search_transcript")}"><span class="muted small" id="tr-count"></span></div>
    <p class="muted small tr-hint">${t("tr_select_hint")}</p><div id="tr-body"></div>`;
  const draw = (q) => {
    const rx = q ? new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i") : null;  // no "g": test() keeps state
    let hits = 0;
    $("#tr-body").innerHTML = secs.map((s) => {
      const lines = lec.segments.filter((g) => g.start >= s.start && g.start < s.end && (!rx || rx.test(g.text)));
      hits += rx ? lines.length : 0;
      if (!lines.length) return "";
      return `<section class="tr-part" id="tr-${s.index}"><h3>${s.index}. ${esc(partTitle(s))}</h3>${lines.map((g) => {
        let text = esc(g.text);
        if (rx) text = text.replace(new RegExp(esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), (m) => `<mark>${m}</mark>`);
        return `<div class="tr-line" data-start="${g.start}">${tsSec(g.start)}<span>${text}</span></div>`;
      }).join("")}</section>`;
    }).join("") || `<p class="muted">${t("no_match")}</p>`;
    $("#tr-count").textContent = rx ? t("lines_n", { n: hits }) : "";
    indexLines();
  };
  draw("");
  $("#tr-q").addEventListener("input", (e) => draw(e.target.value.trim()));
  bindWordFix($("#tr-body"));
}
function drawHints(body) {
  const all = lec.notes.sections.flatMap((s) => (s.exam_hints || []).map((h) => ({ ...h, s })));
  body.innerHTML = all.map((h) => `<div class="hint"><div>“${esc(h.quote)}” ${tsBtn(h.ts)}<span class="where">${h.s.index}. ${esc(h.s.title)}</span></div></div>`).join("");
}
function drawQuiz(body) {
  body.innerHTML = lec.notes.quiz.map((q, i) => `
    <div class="card quiz-item">
      <div class="q"><span class="num">${i + 1}.</span><span>${esc(q.q)} ${tsBtn(q.ts)}</span></div>
      ${q.options.length ? `<ol type="a">${q.options.map((o) => `<li>${esc(o)}</li>`).join("")}</ol>` : ""}
      <button class="btn small" data-reveal="${i}">${t("show_answer")}</button>
      <div class="answer" id="ans-${i}" hidden>${esc(q.a)}</div>
    </div>`).join("");
  $$("[data-reveal]", body).forEach((b) => b.addEventListener("click", () => {
    const a = $(`#ans-${b.dataset.reveal}`);
    a.hidden = !a.hidden;
    b.textContent = a.hidden ? t("show_answer") : t("hide_answer");
  }));
}
function drawCards(body) {
  body.innerHTML = `<p class="muted small" style="margin-bottom:12px">${t("flip_hint")}</p><div class="cards">${lec.notes.flashcards.map((c) => `
    <button class="flip" type="button"><div class="flip-inner">
      <div class="flip-face"><span class="label">${t("question")}</span><span class="front-text">${esc(c.front)}</span></div>
      <div class="flip-face back"><span class="label">${t("answer")}</span><span>${esc(c.back)}</span></div>
    </div></button>`).join("")}</div>`;
  $$(".flip", body).forEach((c) => c.addEventListener("click", () => c.classList.toggle("flipped")));
}
function drawGlossary(body) {
  const terms = [...lec.notes.glossary].sort((a, b) => a.term.localeCompare(b.term));
  body.innerHTML = `<dl class="card glossary">${terms.map((g) => `<div><dt>${esc(g.term)}</dt><dd>${esc(g.definition)} ${tsBtn(g.ts)}</dd></div>`).join("")}</dl>`;
}
function drawTerms(body) {
  // keywords pulled from the slides (plus the lecturer and the course's own terms); the ones in the Whisper
  // prompt were given to speech-to-text as spelling hints
  const inPrompt = (term) => lec.whisper_prompt.includes(term);
  const used = lec.terms.filter((x) => inPrompt(x.term)).length;
  body.innerHTML = `<p class="muted small" style="margin-bottom:12px">${t("terms_hint", { n: lec.terms.length, used })}</p>
    <div class="term-list">${lec.terms.map((x) => `<span class="term ${inPrompt(x.term) ? "used" : ""}"
      title="${x.source === "slides" ? t("terms_on_slides", { n: x.slides }) : esc(t("terms_src_" + x.source))}">${esc(x.term)}${
      x.source === "slides" ? `<small>${x.slides}</small>` : `<small>${esc(t("terms_src_" + x.source))}</small>`}</span>`).join("")}</div>
    <h3 class="sub-head">${t("fixes_done")}</h3>
    ${lec.fixes.length ? `<div class="fix-list">${lec.fixes.map((f) => `<div class="fix"><span class="from">${esc(f.from)}</span> → <b>${esc(f.to)}</b>
      <span class="muted small">${f.count}× · ${t({ auto: "fix_auto", suggestion: "fix_suggestion" }[f.kind] || "fix_course")}</span></div>`).join("")}</div>`
      : `<p class="muted small">${t("fixes_none")}</p>`}
    <h3 class="sub-head">${t("fixes_course", { course: esc(lec.course_name) })}</h3>
    <p class="muted small" style="margin-bottom:10px">${t("fixes_course_hint")}</p>
    <div class="fix-list">${Object.entries(lec.corrections).map(([a, b]) => `<div class="fix"><span class="from">${esc(a)}</span> → <b>${esc(b)}</b>
      <button class="icon-btn" data-unfix="${esc(a)}" title="${t("remove")}">${ICON.x}</button></div>`).join("")}</div>
    <div class="fix-add"><input type="text" id="fix-from" placeholder="${t("fix_from_ph")}"><span>→</span>
      <input type="text" id="fix-to" placeholder="${t("fix_to_ph")}"><button class="btn small" id="fix-add">${t("fix_add")}</button></div>`;
  const save = saveCorrections;
  $("#fix-add").addEventListener("click", () => {
    const a = $("#fix-from").value.trim(), b = $("#fix-to").value.trim();
    if (a && b) save({ ...lec.corrections, [a]: b });
  });
  $("#fix-to").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#fix-add").click(); });
  $$("[data-unfix]", body).forEach((btn) => btn.addEventListener("click", () => {
    const rest = { ...lec.corrections };
    delete rest[btn.dataset.unfix];
    save(rest);
  }));
}
// Save the course's fix list and apply it to this lecture at once (stitch → review: no speech-to-text, no LLM).
// Used by the Keywords tab and by selecting words in the transcript. Keeps the reading position.
async function saveCorrections(corrections) {
  const c = S.courses.find((x) => x.id === lec.course);
  if (!c) return toast(t("not_found"), true);
  const y = window.scrollY;
  try {
    await post("/api/courses", { ...c, corrections });
    S.courses = await api("/api/courses");
    toast(t("fix_applying"));
    await post(`/api/lectures/${encodeURIComponent(lec.id)}/refix`);
    lec = await api(`/api/lectures/${encodeURIComponent(lec.id)}`);
    drawChapters();
    drawTabs();
    window.scrollTo(0, y);
  } catch (e) { toast(e.message, true); }
}

// Transcript: select a word (or a few) → "correct it" pop-up → added to the course's fix list.
function bindWordFix(box) {
  box.addEventListener("mouseup", () => setTimeout(() => {
    const sel = window.getSelection();
    const text = (sel?.toString() || "").trim().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
    if (!text || text.split(/\s+/).length > 4 || text.length > 60) return;
    const line = sel.anchorNode?.parentElement?.closest(".tr-line");
    if (!line || !box.contains(line)) return;
    openWordFix(text, sel.getRangeAt(0).getBoundingClientRect());
  }, 0));
}

function openWordFix(text, rect) {
  closeMenus();
  const m = document.createElement("form");
  m.className = "menu pop word-fix";
  m.innerHTML = `<div class="block-title">${t("fixw_title")}</div>
    <div class="word-fix-row"><span class="from">${esc(text)}</span><span>→</span>
      <input name="to" value="${esc(text)}" aria-label="${t("fixw_title")}" autocomplete="off"></div>
    <p class="muted small">${t("fixw_hint", { course: esc(lec.course_name) })}</p>
    <div class="row-end"><button type="button" class="btn small ghost" data-x>${t("cancel")}</button>
      <button type="submit" class="btn small primary">${t("fixw_apply")}</button></div>`;
  document.body.append(m);
  m.style.left = `${Math.min(window.innerWidth - m.offsetWidth - 8, Math.max(8, rect.left))}px`;
  m.style.top = window.innerHeight - rect.bottom > m.offsetHeight + 12 ? `${rect.bottom + 6}px` : `${Math.max(8, rect.top - m.offsetHeight - 6)}px`;
  const input = m.querySelector("input");
  input.focus();
  input.select();
  m.querySelector("[data-x]").addEventListener("click", closeMenus);
  m.addEventListener("submit", (e) => {
    e.preventDefault();
    const to = input.value.trim();
    closeMenus();
    if (to && to !== text) saveCorrections({ ...lec.corrections, [text]: to });
  });
}

// Term fix suggestions from the LLM on the Mac (termfix.py). Accept = only in that part of this lecture
// (OR/NOR depends on the spot), "whole course" = the course fix list. Re-stitches at once, keeps the scroll.
function drawSuggest(body) {
  const tf = lec.termfix, id = encodeURIComponent(lec.id);
  const again = (label) => `<button class="btn small" id="tf-run">${label}</button>`;
  if (!tf || ["skipped", "failed"].includes(tf.status) || tf.status === "running") {
    const running = tf?.status === "running";
    body.innerHTML = `<div class="empty"><h2>${t(running ? "tf_running" : tf ? "tf_" + tf.status : "tf_none")}</h2>
      <p>${running ? t("tf_running_hint") : tf?.error ? esc(tf.error) : t("tf_none_hint")}</p>
      ${running ? "" : again(t(tf ? "tf_retry" : "tf_make"))}</div>`;
    if (running) poll(async () => {
      const fresh = await api(`/api/lectures/${id}`).catch(() => null);
      if (fresh && fresh.termfix?.status !== "running") { lec = fresh; drawTabs(); }
    }, 5000);
  } else {
    const rows = [...tf.suggestions].sort((a, b) => (a.status !== "open") - (b.status !== "open") || a.at - b.at);
    const ctx = (x) => esc(x.context).replace(new RegExp(esc(x.wrong).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), (m) => `<mark>${m}</mark>`);
    body.innerHTML = `<p class="muted small" style="margin-bottom:12px">${t("tf_hint", { model: esc(tf.model) })}</p>
      ${rows.length ? `<div class="tf-list">${rows.map((x) => `<div class="tf ${x.status}">
        <div class="tf-head">${tsSec(x.at)}<span class="from">${esc(x.wrong)}</span> → <b>${esc(x.right)}</b>
          <span class="muted small">${x.count}×</span></div>
        <div class="tf-ctx muted small">${ctx(x)}</div>
        <div class="tf-act">${x.status === "open"
          ? `<button class="btn small primary" data-tf="${x.id}" data-to="accepted">${t("tf_accept")}</button>
             <button class="btn small" data-tf="${x.id}" data-to="course">${t("tf_course")}</button>
             <button class="btn small ghost" data-tf="${x.id}" data-to="rejected">${t("tf_reject")}</button>`
          : `<span class="tf-state">${t("tf_st_" + x.status)}</span>
             <button class="btn small ghost" data-tf="${x.id}" data-to="open">${t("tf_undo")}</button>`}</div></div>`).join("")}</div>`
        : `<p class="muted">${t("tf_empty")}</p>`}
      <p style="margin-top:16px">${again(t("tf_remake"))}</p>`;
  }
  $("#tf-run")?.addEventListener("click", async () => {
    try { await post(`/api/lectures/${id}/termfix/run`); } catch (e) { return toast(e.message, true); }
    lec = await api(`/api/lectures/${id}`);
    drawTabs();
  });
  $$("[data-tf]", body).forEach((b) => b.addEventListener("click", async () => {
    const y = window.scrollY;
    $$("[data-tf]", body).forEach((x) => { x.disabled = true; });
    try {
      await post(`/api/lectures/${id}/termfix/${b.dataset.tf}`, { status: b.dataset.to });
      lec = await api(`/api/lectures/${id}`);
      if (b.dataset.to === "course") S.courses = await api("/api/courses");
      drawChapters();
      drawTabs();
      window.scrollTo(0, y);
    } catch (e) { toast(e.message, true); drawTabs(); }
  }));
}

function drawReview(body) {
  body.innerHTML = `<div class="card md">${markdown(lec.review || "–")}</div>`;
}
function markdown(src) {  // the subset review.md uses: headings, nested bullets, bold, code, paragraphs
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
  let html = "", depth = 0;
  const close = (to) => { while (depth > to) { html += "</ul>"; depth--; } };
  for (const line of src.split("\n")) {
    const m = line.match(/^(\s*)- (.*)/);
    if (m) {
      const d = Math.floor(m[1].length / 2) + 1;
      while (depth < d) { html += "<ul>"; depth++; }
      close(d);
      html += `<li>${inline(m[2])}</li>`;
      continue;
    }
    close(0);
    const h = line.match(/^(#{1,3}) (.*)/);
    if (h) html += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`;
    else if (line.trim()) html += `<p>${inline(line)}</p>`;
  }
  close(0);
  return html;
}
