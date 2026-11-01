// Setup: speech-to-text, notes model, outputs, courses, keys, worker + usage.
import { api, post } from "../core/api.js";
import { $, $$, view } from "../core/dom.js";
import { esc, fmtSem } from "../core/format.js";
import { ICON } from "../core/icons.js";
import { S, courseKey, reason } from "../core/state.js";
import { scroller, setTheme, themeChoice, toast } from "../core/ui.js";
import { route } from "../core/router.js";
import { startWorker } from "../shared/actions.js";
import { bindModels, notesSectionHtml, sttSectionHtml } from "./setup-models.js";

let editingCourse = null;

// "2026-27 S1" shifted by k semesters (k < 0: earlier)
function semShift(name, k) {
  let year = Number(name.slice(0, 4)), sem = Number(name.slice(-1)) - 1 + k;
  year += Math.floor(sem / 2);
  sem = ((sem % 2) + 2) % 2;
  return `${year}-${String((year + 1) % 100).padStart(2, "0")} S${sem + 1}`;
}
// the semesters offered in the course form: next one, the current one, the four before (+ the course's own)
function semesterChoices(own) {
  const cur = S.sem?.current;
  if (!cur) return own ? [own] : [];
  const list = [1, 0, -1, -2, -3, -4].map((k) => semShift(cur, k));
  return own && !list.includes(own) ? [...list, own] : list;
}

// refresh = true after a change on this page: fetch first, then swap the content in one go and keep the scroll
// position (showing "Loading…" first collapsed the page, so every change jumped to the top and faded in again)
export async function renderSetup(refresh = false) {
  const y = scroller().scrollTop;
  if (!refresh) view.innerHTML = `<div class="loading">${t("loading")}</div>`;
  let status;
  try {
    [S.setup, S.courses, status, S.sem] = await Promise.all([api("/api/setup"), api("/api/courses"), api("/api/status"),
      api("/api/semesters")]);
  } catch (e) { toast(e.message, true); return; }
  const s = S.setup;
  const opt = (on, ok, title, desc, attrs, statusTxt) => `
    <button type="button" class="option ${on ? "on" : ""} ${ok ? "" : "off"}" ${attrs}>
      <span class="option-top">${esc(title)}<span class="pill ${on && ok ? "ok" : ok ? "" : "bad"}">${statusTxt}</span></span>
      <p>${esc(desc)}</p></button>`;
  view.innerHTML = `
    <h1 class="large-title">${t("setup_title")}</h1>
    <div class="settings-grid setup ${refresh ? "" : "page-enter"}">
      ${sttSectionHtml(s)}

      <section class="setup-section">
        <h2>${t("s_mac")}</h2><p class="muted small">${t("s_mac_sub")}</p>
        <div class="list"><div class="key-row">
          <span><b>${t("mac_url")}</b></span>
          <input type="text" id="mac-url" value="${esc(s.mac.url || "")}" placeholder="http://macbook-pro:7862" autocomplete="off" spellcheck="false">
          <span style="display:flex;gap:6px"><button class="btn btn-small" id="mac-save">${t("c_save")}</button>
            <button class="btn btn-small btn-plain" id="mac-test">${t("mac_test")}</button></span>
        </div>
        <div class="key-row">
          <span><b>${t("mac_token")}</b> <span class="pill ${s.mac.token ? "ok" : ""}">${s.mac.token ? t("k_set") : t("k_missing")}</span></span>
          <input type="password" data-key="mac" placeholder="${t("mac_token_ph")}" autocomplete="off">
          <span><button class="btn btn-small" data-savekey="mac">${t("c_save")}</button></span>
        </div></div>
        <p class="muted small" id="mac-result" aria-live="polite"></p>
      </section>

      <section class="setup-section">
        <h2>${t("s_hub")}</h2><p class="muted small">${t("s_hub_sub")}</p>
        <div class="list"><div class="key-row">
          <span><b>${t("mac_url")}</b></span>
          <input type="text" id="hub-url" value="${esc(s.hub.url || "")}" autocomplete="off" spellcheck="false">
          <span><button class="btn btn-small" id="hub-save">${t("c_save")}</button></span>
        </div>
        <div class="key-row">
          <span><b>${t("hub_code")}</b> <span class="pill ${s.hub.code ? "ok" : ""}">${s.hub.code ? t("k_set") : t("k_missing")}</span></span>
          <input type="password" data-key="hub" autocomplete="off">
          <span><button class="btn btn-small" data-savekey="hub">${t("c_save")}</button></span>
        </div></div>
        <div><button class="btn btn-small" id="hub-import" ${s.hub.url && s.hub.code ? "" : "disabled"}>${t("hub_import")}</button></div>
        <p class="muted small" id="hub-result" aria-live="polite"></p>
      </section>

      ${notesSectionHtml(s)}

      <section class="setup-section">
        <h2>${t("s_outputs")}</h2><p class="muted small">${t("s_outputs_sub")}</p>
        <div class="list">${["exam_hints", "quiz", "flashcards", "glossary"].map((k) => `
          <label class="row toggle-row"><span class="row-text"><b>${t("o_" + k)}</b><span class="label">${t("o_" + k + "_d")}</span></span>
            <input type="checkbox" class="switch" data-out="${k}" ${s.outputs[k] ? "checked" : ""}></label>`).join("")}</div>
      </section>

      <section class="setup-section" id="courses-section">
        <h2>${t("s_courses")}</h2><p class="muted small">${t("s_courses_sub")}</p>
        <div class="list" id="course-list"></div>
      </section>

      <section class="setup-section">
        <h2>${t("s_keys")}</h2><p class="muted small">${t("s_keys_sub")}</p>
        <div class="list">${[["groq", "Groq", "https://console.groq.com/keys"], ["gemini", "Gemini", "https://aistudio.google.com/apikey"]].map(([k, label, url]) => `
          <div class="key-row">
            <span><b>${label}</b> <span class="pill ${s.keys[k] ? "ok" : ""}">${s.keys[k] ? t("k_set") : t("k_missing")}</span></span>
            <input type="password" data-key="${k}" placeholder="${t("k_paste")}" autocomplete="off">
            <span style="display:flex;gap:6px"><button class="btn btn-small" data-savekey="${k}">${t("k_save")}</button>
              <a class="btn btn-small btn-plain" href="${url}" target="_blank" rel="noopener">${t("k_get")}</a></span>
          </div>`).join("")}</div>
      </section>

      <section class="setup-section">
        <h2>${t("s_worker")}</h2><p class="muted small">${t("s_worker_sub")}</p>
        <div class="card flat-row"><span class="pill ${s.worker ? "ok" : "bad"}">${s.worker ? t("worker_on") : t("worker_off")}</span>
          ${s.worker ? "" : `<button class="btn btn-small btn-primary" id="setup-start">${t("worker_start")}</button>`}</div>
        <h3 class="group-title">${t("s_usage")}</h3>
        <div class="card meters">${Object.entries(status.quotas).map(([name, windows]) => Object.entries(windows).filter(([w]) => /day/.test(w)).map(([w, [used, limit]]) => `
          <div class="meter"><span>${esc(name)}</span><span class="muted">${Math.round(used)} / ${Math.round(limit)}</span>
            <div class="progress"><span style="width:${Math.min(100, (used / (limit || 1)) * 100)}%"></span></div><span class="muted small">${esc(w)}</span></div>`).join("")).join("")}</div>
      </section>

      <section class="setup-section">
        <h2>${t("s_look")}</h2>
        <div class="segmented" role="group" aria-label="${t("s_look")}">
          ${[["system", t("theme_system")], ["light", t("theme_light")], ["dark", t("theme_dark")]].map(([key, label]) =>
            `<button type="button" aria-pressed="${themeChoice() === key}" data-theme-choice="${key}">${esc(label)}</button>`).join("")}
        </div>
      </section>

      <section class="setup-section">
        <h2>${t("s_language")}</h2>
        <div class="segmented" role="group" aria-label="${t("s_language")}">
          ${[["nl", "Nederlands"], ["en", "English"]].map(([key, label]) =>
            `<button type="button" aria-pressed="${LANG === key}" data-lang="${key}">${label}</button>`).join("")}
        </div>
      </section>
    </div>`;
  const rerender = () => renderSetup(true);
  const apply = async (path, body) => {
    try { await post(path, body); toast(t("saved")); } catch (e) { toast(e.message, true); }
    rerender();
  };
  bindModels(s, rerender);
  $$("[data-theme-choice]").forEach((b) => b.addEventListener("click", () => { setTheme(b.dataset.themeChoice); rerender(); }));
  $$("[data-lang]").forEach((b) => b.addEventListener("click", () => { setLang(b.dataset.lang); route(); }));
  $$("[data-model]").forEach((b) => b.addEventListener("click", () => apply("/api/setup/notes-model", { value: b.dataset.model })));
  $$("[data-out]").forEach((c) => c.addEventListener("change", () => apply("/api/setup/outputs", { [c.dataset.out]: c.checked })));
  $$("[data-savekey]").forEach((b) => b.addEventListener("click", () => {
    const input = $(`[data-key="${b.dataset.savekey}"]`);
    if (input.value.trim()) apply("/api/setup/key", { name: b.dataset.savekey, value: input.value.trim() });
  }));
  $("#setup-start")?.addEventListener("click", startWorker);
  $("#hub-save").addEventListener("click", () => apply("/api/setup/hub", { url: $("#hub-url").value.trim() }));
  $("#hub-import").addEventListener("click", async (e) => {
    const out = $("#hub-result");
    e.currentTarget.disabled = true;
    try {
      const r = await post("/api/setup/hub/import");
      out.textContent = t("hub_imported", { linked: r.linked, added: r.added });
      drawCourses();
    } catch (err) { out.textContent = err.message; }
    e.currentTarget.disabled = false;
  });
  $("#mac-save").addEventListener("click", () => apply("/api/setup/mac", { url: $("#mac-url").value.trim() }));
  $("#mac-test").addEventListener("click", async (e) => {
    const out = $("#mac-result");
    e.currentTarget.disabled = true;
    out.textContent = t("mac_testing");
    try {
      const r = await post("/api/setup/mac/test");
      out.innerHTML = r.ok ? `<span class="pill ok">${t("mac_ok")}</span> Whisper: ${esc(r.whisper)} · ${t("mac_suggest")}: ${esc(r.llm)} · ${r.ms} ms`
        : `<span class="pill bad">${t("mac_fail")}</span> ${esc(r.detail || r.whisper || "")}`;
    } catch (err) { out.textContent = err.message; }
    e.currentTarget.disabled = false;
  });
  drawCourses();
  if (refresh) scroller().scrollTop = y;
}

function drawCourses() {
  const box = $("#course-list");
  if (!box) return;
  const form = (c) => `
    <div class="course-form">
      <label class="form-field">${t("c_name")}<input type="text" id="cf-name" value="${esc(c.name || "")}"></label>
      <label class="form-field">${t("c_lang")}<select id="cf-lang">
        <option value="nl" ${c.language !== "en" ? "selected" : ""}>Nederlands</option>
        <option value="en" ${c.language === "en" ? "selected" : ""}>English</option></select></label>
      <label class="form-field">${t("c_lecturer")}<input type="text" id="cf-lecturer" value="${esc(c.lecturer || "")}"></label>
      <label class="form-field">${t("c_semester")}<select id="cf-sem">
        <option value="">${esc(t("c_sem_auto", { sem: S.sem?.courses[c.id] && !c.semester ? fmtSem(S.sem.courses[c.id].semester) : "…" }))}</option>
        ${semesterChoices(c.semester).map((x) => `<option value="${x}" ${x === c.semester ? "selected" : ""}>${esc(fmtSem(x))}</option>`).join("")}
      </select></label>
      <label class="form-field wide">${t("c_terms")}<input type="text" id="cf-terms" value="${esc((c.extra_terms || []).join(", "))}"></label>
      <label class="form-field wide">${t("c_fixes")}<textarea id="cf-fixes" rows="3" placeholder="nent = NAND">${esc(Object.entries(c.corrections || {}).map(([a, b]) => `${a} = ${b}`).join("\n"))}</textarea></label>
      <div class="row-end"><button class="btn btn-small" id="cf-cancel">${t("cancel")}</button><button class="btn btn-small btn-primary" id="cf-save">${t("c_save")}</button></div>
    </div>`;
  box.innerHTML = S.courses.map((c) => editingCourse === c.id ? form(c) : `
    <div class="row course-row" data-course="${courseKey(c.id)}">
      <span class="dot"></span>
      <span class="row-text"><b>${esc(c.name)}</b><span class="label">${c.language === "en" ? "English" : "Nederlands"}${c.lecturer ? ` · ${esc(c.lecturer)}` : ""}${c.extra_terms?.length ? ` · ${esc(c.extra_terms.join(", "))}` : ""}${Object.keys(c.corrections || {}).length ? ` · ${t("c_fixes_n", { n: Object.keys(c.corrections).length })}` : ""}</span></span>
      <button class="btn btn-small btn-plain" data-edit="${esc(c.id)}">${t("c_edit")}</button>
      <button class="icon-btn" data-del="${esc(c.id)}" title="${t("c_delete")}">${ICON.trash}</button>
    </div>`).join("") + (editingCourse === "new" ? form({}) : `<div class="row"><button class="btn btn-small" id="c-add">${t("c_add")}</button></div>`);
  $("#c-add")?.addEventListener("click", () => { editingCourse = "new"; drawCourses(); });
  $$("[data-edit]", box).forEach((b) => b.addEventListener("click", () => { editingCourse = b.dataset.edit; drawCourses(); }));
  $$("[data-del]", box).forEach((b) => b.addEventListener("click", async () => {
    const c = S.courses.find((x) => x.id === b.dataset.del);
    if (!confirm(t("c_confirm_delete", { name: c.name }))) return;
    try { await api(`/api/courses/${encodeURIComponent(c.id)}`, { method: "DELETE" }); S.courses = await api("/api/courses"); drawCourses(); }
    catch (e) { toast(e.message, true); }
  }));
  $("#cf-cancel")?.addEventListener("click", () => { editingCourse = null; drawCourses(); });
  $("#cf-save")?.addEventListener("click", async () => {
    const old = S.courses.find((c) => c.id === editingCourse) || {};
    const fixes = Object.fromEntries($("#cf-fixes").value.split("\n").map((l) => l.split("=").map((x) => x.trim())).filter(([a, b]) => a && b));
    const body = { ...old, id: editingCourse === "new" ? null : editingCourse, name: $("#cf-name").value.trim(), language: $("#cf-lang").value,
      lecturer: $("#cf-lecturer").value.trim() || null,
      // a chosen semester decides archiving again (archived: automatic), so "2026-27 S1" puts it in your list
      semester: $("#cf-sem").value || null, archived: ($("#cf-sem").value || null) !== (old.semester || null) ? null : old.archived ?? null,
      extra_terms: $("#cf-terms").value.split(",").map((x) => x.trim()).filter(Boolean),
      corrections: fixes };
    if (!body.name) return;
    try { await post("/api/courses", body); toast(t("saved")); editingCourse = null; S.courses = await api("/api/courses"); drawCourses(); }
    catch (e) { toast(e.message, true); }
  });
}
