// Settings → Share: a link per person (name + courses) to watch your lectures at <hub>/share/, without Sequo.
// The codes live on the hub; Verbatim keeps the shared lectures there up to date (share.py, worker idle round).
import { api, post } from "../core/api.js";
import { $, $$ } from "../core/dom.js";
import { esc } from "../core/format.js";
import { S, courseKey, isArchived, sortedCourses } from "../core/state.js";
import { toast, toastAction } from "../core/ui.js";

let data = null, editing = null, timer = null;
const colorsOf = (ids) => Object.fromEntries(ids.map((id) => [id, courseKey(id)]));
const hidden = new Set();  // codes being revoked (undo window)

export const shareSectionHtml = () => `<section class="setup-section" id="share-section">
    <h2>${t("s_share")}</h2><p class="muted small share-intro">${t("share_intro")}</p>
    <div id="share-body"><div class="loading">${t("loading")}</div></div>
  </section>`;

export async function bindShare() {
  clearTimeout(timer);
  try { data = await api("/api/share"); } catch (e) { toast(e.message, true); return; }
  if (!$("#share-body")) return;  // left the tab meanwhile
  draw();
  if (data.syncing) timer = setTimeout(bindShare, 3000);
}

const courseChecks = (chosen, name) => sortedCourses().filter((c) => !isArchived(c.id) || chosen.includes(c.id)).map((c) => `
  <label class="row toggle-row"><span class="row-text"><b>${esc(c.name)}</b></span>
    <input type="checkbox" class="switch" name="${name}" value="${esc(c.id)}" ${chosen.includes(c.id) ? "checked" : ""}></label>`).join("");

function statusLine() {
  const st = data.status;
  if (data.syncing) return t("share_syncing");
  if (data.sync_error) return t("share_failed", { e: data.sync_error });
  if (!st) return "";
  return [t("share_count", { n: st.shared }), st.videos_waiting ? t("share_waiting", { n: st.videos_waiting }) : ""]
    .filter(Boolean).join(" · ");
}

function draw() {
  const body = $("#share-body");
  if (!data.hub) {
    body.innerHTML = `<div class="card"><p>${t("share_no_hub")}</p></div>`;
    return;
  }
  if (data.error) {
    body.innerHTML = `<div class="card"><p>${t("share_hub_error")}</p><p class="muted small">${esc(data.error)}</p></div>`;
    return;
  }
  const codes = data.codes.filter((c) => !hidden.has(c.id));
  const names = (c) => c.courses.map((x) => S.courses.find((k) => k.id === x.id)?.name || x.name).join(", ") || t("share_no_courses");
  body.innerHTML = `
    ${codes.length ? `<h3 class="group-title">${t("share_links")}</h3><ul class="list">${codes.map((c) => `
      <li><div class="row share-row">
        <span class="row-main"><span class="row-title">${esc(c.name)}</span><span class="sub">${esc(names(c))}</span></span>
        <span class="share-actions">
          <button class="btn btn-small" data-copy="${esc(c.id)}">${t("share_copy")}</button>
          <button class="btn btn-small btn-plain" data-edit="${esc(c.id)}" aria-expanded="${editing === c.id}">${t("share_courses")}</button>
          <button class="btn btn-small btn-plain btn-danger" data-revoke="${esc(c.id)}">${t("share_revoke")}</button>
        </span></div></li>
      ${editing === c.id ? `<li class="share-edit"><div class="list">${courseChecks(c.courses.map((x) => x.id), "edit-course")}</div>
        <div class="share-form-actions"><button class="btn btn-small btn-primary" data-save="${esc(c.id)}">${t("c_save")}</button></div></li>` : ""}`).join("")}</ul>` : ""}
    <h3 class="group-title">${t("share_new")}</h3>
    <div class="list">
      <div class="key-row"><label for="share-name"><b>${t("share_name")}</b></label>
        <input type="text" id="share-name" maxlength="80" placeholder="${t("share_name_ph")}" autocomplete="off"><span></span></div>
      ${courseChecks([], "new-course")}
    </div>
    <div class="share-form-actions"><button class="btn btn-primary" id="share-make">${t("share_make")}</button></div>
    <div class="share-status"><span class="muted small" aria-live="polite">${esc(statusLine())}</span>
      <button class="btn btn-small btn-plain" id="share-sync" ${data.syncing ? "disabled" : ""}>${t("share_sync")}</button></div>`;
  bind();
}

async function copy(link) {
  try { await navigator.clipboard.writeText(link); toast(t("share_copied")); }
  catch { window.prompt(t("share_copy"), link); }
}

function bind() {
  const find = (id) => data.codes.find((c) => c.id === id);
  $$("[data-copy]").forEach((b) => b.addEventListener("click", () => copy(find(b.dataset.copy).link)));
  $$("[data-edit]").forEach((b) => b.addEventListener("click", () => { editing = editing === b.dataset.edit ? null : b.dataset.edit; draw(); }));
  $$("[data-save]").forEach((b) => b.addEventListener("click", async () => {
    const courses = $$('input[name="edit-course"]:checked').map((i) => i.value);
    try { await api(`/api/share/codes/${b.dataset.save}`, { method: "PATCH", json: { courses, colors: colorsOf(courses) } }); toast(t("saved")); editing = null; }
    catch (e) { toast(e.message, true); }
    bindShare();
  }));
  $$("[data-revoke]").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.revoke;
    hidden.add(id);
    draw();
    // no confirmation dialog: 5 s to undo, then the code stops working
    toastAction(t("share_revoked", { name: find(id).name }), t("undo"), {
      onAction: () => { hidden.delete(id); draw(); },
      onTimeout: async () => {
        try { await api(`/api/share/codes/${id}`, { method: "DELETE" }); } catch (e) { toast(e.message, true); }
        hidden.delete(id);
        bindShare();
      },
    });
  }));
  $("#share-make")?.addEventListener("click", async () => {
    const name = $("#share-name").value.trim();
    const courses = $$('input[name="new-course"]:checked').map((i) => i.value);
    if (!name) { $("#share-name").focus(); toast(t("share_need_name"), true); return; }
    if (!courses.length) { toast(t("share_need_course"), true); return; }
    try {
      const code = await post("/api/share/codes", { name, courses, colors: colorsOf(courses) });
      await copy(code.link);
    } catch (e) { toast(e.message, true); }
    bindShare();
  });
  $("#share-sync")?.addEventListener("click", async () => {
    try { await post("/api/share/sync"); } catch (e) { toast(e.message, true); }
    bindShare();
  });
}
