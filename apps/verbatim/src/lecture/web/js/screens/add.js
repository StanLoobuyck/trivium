// Add recordings (#/add): page around the upload panel (screens/upload.js).
import { view } from "../core/dom.js";
import { drawUpload } from "./upload.js";

export function renderAdd() {
  view.innerHTML = `
    <div><h1>${t("add_title")}</h1><p class="muted" style="margin-top:4px">${t("add_sub")}</p></div>
    <section class="card upload fade-in" id="upload"></section>`;
  drawUpload();
}
