// Welcome (#/welcome): the first start in simple mode (Windows installer). One step per screen:
// language → Groq key (speech to text; may be skipped) → Gemini key (notes; optional) → how lectures come in.
// Keys are tested with the service and saved only when they work (/api/setup/key/test).
import { icon } from "/static/design/icons.js";
import { api, post } from "../core/api.js";
import { $, $$, view } from "../core/dom.js";
import { esc } from "../core/format.js";
import { S } from "../core/state.js";
import { toast } from "../core/ui.js";

const STEPS = ["lang", "groq", "gemini", "ready"];
const KEY_URL = { groq: "https://console.groq.com/keys", gemini: "https://aistudio.google.com/apikey" };
const TRIVIUM_URL = "https://stanloobuyck.github.io/trivium/";

let step = 0, skipping = false;
const result = { groq: null, gemini: null };  // last test result per key: {ok, reason}

export async function renderWelcome() {
  if (!S.setup) S.setup = await api("/api/setup").catch(() => null);
  draw(true);
}

function dots() {
  return `<div class="welcome-dots" aria-label="${esc(t("w_step", { n: step + 1, total: STEPS.length }))}">${STEPS.map((_, i) =>
    `<span class="${i === step ? "on" : ""}"></span>`).join("")}</div>`;
}

function keyStep(name) {
  const have = !!S.setup?.keys?.[name], r = result[name];
  const status = r ? (r.ok ? `<span class="pill ok">${t("w_key_ok")}</span>` : `<span class="pill bad">${esc(t("w_key_" + r.reason))}</span>`)
    : have ? `<span class="pill ok">${t("w_key_have")}</span>` : "";
  return `
    <h1 class="large-title">${t(`w_${name}_title`)}</h1>
    <p class="welcome-lead">${t(`w_${name}_lead`)}</p>
    <ol class="welcome-steps">
      <li><span>${t(`w_${name}_get`)}</span>
        <a class="btn btn-small" href="${KEY_URL[name]}" target="_blank" rel="noopener">${t(`w_${name}_open`)} ↗</a></li>
      <li><label class="form-field" for="w-key">${t("w_key_paste")}</label>
        <div class="welcome-key"><input type="password" id="w-key" autocomplete="off" spellcheck="false" placeholder="${t("k_paste")}">
          <button class="btn btn-small btn-primary" id="w-test">${t("w_key_test")}</button></div>
        <p class="welcome-status" id="w-status" aria-live="polite">${status}</p></li>
    </ol>`;
}

function body() {
  const name = STEPS[step];
  if (name === "lang") return `
    <h1 class="large-title">${t("w_title")}</h1>
    <p class="welcome-lead">${t("w_lead")}</p>
    <h2 class="group-title">${t("s_language")}</h2>
    <div class="segmented" role="group" aria-label="${t("s_language")}">
      ${[["nl", "Nederlands"], ["en", "English"]].map(([key, label]) =>
        `<button type="button" aria-pressed="${LANG === key}" data-lang="${key}">${label}</button>`).join("")}
    </div>`;
  if (name === "groq") return keyStep("groq") + (skipping ? `
    <div class="card welcome-warn" role="note"><p>${t("w_groq_skip_warn")}</p>
      <div class="row-end"><button class="btn btn-small" id="w-skip-no">${t("cancel")}</button>
        <button class="btn btn-small" id="w-skip-yes">${t("w_skip_anyway")}</button></div></div>` : "");
  if (name === "gemini") return keyStep("gemini") + `<p class="muted small">${t("w_gemini_note")}</p>`;
  return `
    <h1 class="large-title">${t("w_ready_title")}</h1>
    <p class="welcome-lead">${t("w_ready_lead")}</p>
    <div class="list welcome-ways">
      <a class="row" href="${TRIVIUM_URL}" target="_blank" rel="noopener">${icon("download")}<span class="row-main"><span><b>${t("w_ready_velox")}</b>
        <span class="sub">${t("w_ready_velox_d")}</span></span></span>${icon("chevron")}</a>
      <button type="button" class="row" id="w-add">${icon("plus")}<span class="row-main"><span><b>${t("w_ready_add")}</b>
        <span class="sub">${t("w_ready_add_d")}</span></span></span>${icon("chevron")}</button>
    </div>
    ${S.setup?.keys?.groq ? "" : `<p class="muted small">${t("w_ready_nogroq")}</p>`}`;
}

function nav() {
  const name = STEPS[step];
  const back = step ? `<button class="btn" id="w-back">${t("w_back")}</button>` : "<span></span>";
  if (name === "lang") return `${back}<button class="btn btn-primary" id="w-next">${t("w_next")}</button>`;
  if (name === "groq") {
    const ok = !!S.setup?.keys?.groq;
    return `${back}<span class="welcome-nav-end">${ok ? "" : `<button class="btn btn-plain" id="w-skip">${t("w_skip")}</button>`}
      <button class="btn btn-primary" id="w-next" ${ok ? "" : "disabled"}>${t("w_next")}</button></span>`;
  }
  if (name === "gemini") {
    const ok = !!S.setup?.keys?.gemini;
    return `${back}<button class="btn ${ok ? "btn-primary" : ""}" id="w-next">${t(ok ? "w_next" : "w_no_notes")}</button>`;
  }
  return `${back}<button class="btn btn-primary" id="w-done">${t("w_start")}</button>`;
}

function draw(enter = false) {  // enter: a new step (animated); otherwise the same step updates in place
  view.innerHTML = `<div class="welcome">${dots()}<div class="welcome-body ${enter ? "page-enter" : ""}">${body()}</div>
    <div class="welcome-nav">${nav()}</div></div>`;
  bind();
}

const go = (to) => { step = Math.max(0, Math.min(STEPS.length - 1, to)); skipping = false; draw(true); $("#view").focus?.(); };

async function test(name) {
  const input = $("#w-key"), button = $("#w-test");
  if (!input.value.trim()) { input.focus(); return; }
  button.disabled = true;
  $("#w-status").innerHTML = `<span class="pill">${t("w_key_testing")}</span>`;
  try {
    result[name] = await post("/api/setup/key/test", { name, value: input.value });
  } catch (e) {
    result[name] = { ok: false, reason: "error" };
    toast(e.message, true);
  }
  if (result[name].ok) S.setup = await api("/api/setup").catch(() => S.setup);
  draw();
  if (!result[name].ok) $("#w-key").focus();
}

function bind() {
  $("#w-back")?.addEventListener("click", () => go(step - 1));
  $("#w-next")?.addEventListener("click", () => go(step + 1));
  $$("[data-lang]").forEach((b) => b.addEventListener("click", () => {
    setLang(b.dataset.lang);
    $$("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
    draw();
  }));
  const name = STEPS[step];
  if (name === "groq" || name === "gemini") {
    $("#w-test").addEventListener("click", () => test(name));
    $("#w-key").addEventListener("keydown", (e) => { if (e.key === "Enter") test(name); });
  }
  $("#w-skip")?.addEventListener("click", () => { skipping = true; draw(); $("#w-skip-yes")?.focus(); });
  $("#w-skip-no")?.addEventListener("click", () => { skipping = false; draw(); });
  $("#w-skip-yes")?.addEventListener("click", () => go(step + 1));
  const finish = async (to) => {
    try { await post("/api/setup/welcome-done"); } catch (e) { toast(e.message, true); return; }
    if (S.setup) S.setup.welcomed = true;
    location.hash = to;
  };
  $("#w-done")?.addEventListener("click", () => finish("#/"));
  $("#w-add")?.addEventListener("click", () => finish("#/add"));
}
