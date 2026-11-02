// Settings › speech-to-text order and notes models: ranked lists with Test / ↑↓ / Remove, and the
// "Add a model" form (backend: /api/models, src/lecture/models.py).
import { api, post } from "../core/api.js";
import { $, $$ } from "../core/dom.js";
import { esc } from "../core/format.js";
import { reason } from "../core/state.js";
import { toast } from "../core/ui.js";

const STT_PRESETS = ["mac", "groq"];
const NOTES_PRESETS = ["ollama-mac", "groq", "openrouter", "claude", "gemini", "openai"];
let adding = null;  // "stt" | "notes" while that section's form is open

const dot = (ok) => `<span class="status-dot ${ok ? "" : "bad"}" aria-hidden="true"></span>`;
const rowBtn = (attrs, label, text = label) => `<button type="button" class="btn btn-small btn-plain" ${attrs} aria-label="${esc(label)}">${text}</button>`;

export function sttSectionHtml(s) {
  const order = s.stt.order;
  return `<section class="setup-section">
    <h2>${t("s_stt")}</h2><p class="muted small">${t("m_order_hint")}</p>
    <ol class="list rank">${order.map((o, i) => `
      <li class="rank-row ${o.entry === s.stt.active_provider ? "on" : ""}">
        <span class="rank-n">${i + 1}</span>
        <span class="rank-what"><b>${esc(o.label)}</b><span class="muted small">${dot(o.ok)}${esc(o.ok ? (o.entry === s.stt.active_provider ? t("active_now") : t("ok")) : o.detail || t("not_ok"))}</span></span>
        <span class="rank-actions">
          <span class="test-out muted small" data-test-out="stt:${esc(o.entry)}"></span>
          ${rowBtn(`data-test="stt" data-entry="${esc(o.entry)}"`, t("m_test"))}
          ${rowBtn(`data-move="-1" data-i="${i}" ${i === 0 ? "disabled" : ""}`, t("m_up"), "↑")}
          ${rowBtn(`data-move="1" data-i="${i}" ${i === order.length - 1 ? "disabled" : ""}`, t("m_down"), "↓")}
          ${o.custom ? rowBtn(`data-remove="${esc(o.entry.slice(7))}"`, t("m_remove")) : ""}
        </span>
      </li>`).join("")}</ol>
    ${adding === "stt" ? formHtml("stt") : `<div><button type="button" class="btn btn-small" data-add="stt">${t("m_add_stt")}</button></div>`}
    <div class="list"><label class="row toggle-row"><span class="row-text"><b>${t("m_battery")}</b><span class="sub">${t(s.stt.on_battery ? "m_battery_now" : "m_battery_d")}</span></span>
      <input type="checkbox" class="switch" id="skip-battery" ${s.stt.skip_on_battery ? "checked" : ""}></label></div>
  </section>`;
}

export function notesSectionHtml(s) {
  return `<section class="setup-section">
    <h2>${t("s_notes")}</h2>
    <ol class="list rank">${s.notes.choices.map((c) => `
      <li class="rank-row ${c.value === s.notes.choice ? "on" : ""}">
        <button type="button" class="rank-what rank-pick" data-model="${esc(c.value)}">
          <b>${esc(c.label)}${c.value === s.notes.choice ? ` <span class="muted small">· ${t("m_main")}</span>` : ""}</b>
          <span class="muted small">${dot(c.ok)}${esc(reason(c.detail))}</span></button>
        <span class="rank-actions">
          <span class="test-out muted small" data-test-out="notes:${esc(c.value)}"></span>
          ${rowBtn(`data-test="notes" data-entry="${esc(c.value)}"`, t("m_test"))}
          ${c.value.startsWith("custom:") ? rowBtn(`data-remove="${esc(c.value.slice(7))}"`, t("m_remove")) : ""}
        </span>
      </li>`).join("")}</ol>
    ${adding === "notes" ? formHtml("notes") : `<div><button type="button" class="btn btn-small" data-add="notes">${t("m_add_notes")}</button></div>`}
  </section>`;
}

function formHtml(kind) {
  const presets = kind === "stt" ? STT_PRESETS : NOTES_PRESETS;
  return `<form class="add-model panel" id="add-model" data-kind="${kind}">
    <h3>${t("m_add_title")}</h3>
    <div class="add-model-grid">
      <label class="form-field">${t("m_preset")}<select name="preset">${presets.map((p) => `<option value="${p}">${esc(t("p_" + p))}</option>`).join("")}</select></label>
      <label class="form-field">${t("m_model")}<input name="model" required placeholder="${t("m_model_ph")}"></label>
      <label class="form-field">${t("m_label")}<input name="label" placeholder="${t("m_label_ph")}"></label>
      <label class="form-field only-openai" hidden>${t("m_base")}<input name="base_url" placeholder="http://localhost:1234/v1"></label>
      <label class="form-field only-openai" hidden>${t("m_key")}<input name="key_name" placeholder="${t("m_key_ph")}"></label>
    </div>
    <div class="row-end"><span class="error" id="add-model-error"></span>
      <button type="button" class="btn btn-small" id="add-model-cancel">${t("cancel")}</button>
      <button type="submit" class="btn btn-small btn-primary">${t("m_add")}</button></div>
  </form>`;
}

// rerender(): redraw the Settings page after a change
export function bindModels(s, rerender) {
  $("#skip-battery")?.addEventListener("change", async (e) => {
    try { await post("/api/setup/stt-battery", { value: e.target.checked }); toast(t("saved")); } catch (err) { toast(err.message, true); }
    rerender();
  });
  $$("[data-add]").forEach((b) => b.addEventListener("click", () => { adding = b.dataset.add; rerender(); }));
  $$("[data-test]").forEach((b) => b.addEventListener("click", async () => {
    const out = $(`[data-test-out="${b.dataset.test}:${CSS.escape(b.dataset.entry)}"]`);
    out.textContent = t("m_testing");
    b.disabled = true;
    try {
      const r = await post("/api/models/test", { kind: b.dataset.test, entry: b.dataset.entry });
      out.textContent = r.ok ? t("m_test_ok", { s: r.seconds }) : t("m_test_fail", { detail: r.detail });
      out.classList.toggle("bad-text", !r.ok);
    } catch (e) { out.textContent = e.message; }
    b.disabled = false;
  }));
  $$("[data-move]").forEach((b) => b.addEventListener("click", async () => {
    const order = s.stt.order.map((o) => o.entry);
    const i = Number(b.dataset.i), j = i + Number(b.dataset.move);
    [order[i], order[j]] = [order[j], order[i]];
    try { await post("/api/models/order", { order }); } catch (e) { toast(e.message, true); }
    rerender();
  }));
  $$("[data-remove]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/api/models/${encodeURIComponent(b.dataset.remove)}`, { method: "DELETE" }); toast(t("saved")); }
    catch (e) { toast(e.message, true); }
    rerender();
  }));
  const form = $("#add-model");
  if (!form) return;
  const syncOpenai = () => $$(".only-openai", form).forEach((el) => { el.hidden = form.preset.value !== "openai"; });
  form.preset.addEventListener("change", syncOpenai);
  syncOpenai();
  form.model.focus();
  $("#add-model-cancel").addEventListener("click", () => { adding = null; rerender(); });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = { kind: form.dataset.kind, preset: form.preset.value, model: form.model.value.trim(), label: form.label.value.trim(),
      base_url: form.base_url.value.trim() || null, key_name: form.key_name.value.trim() || null };
    try { await post("/api/models", body); adding = null; toast(t("saved")); rerender(); }
    catch (err) { $("#add-model-error").textContent = err.message; }
  });
}
