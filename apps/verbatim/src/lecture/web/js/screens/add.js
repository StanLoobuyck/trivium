// Add recordings (#/add): page around the upload panel (screens/upload.js).
import { view } from "../core/dom.js";
import { drawUpload } from "./upload.js";

export function renderAdd() {
  view.innerHTML = `
    <h1 class="large-title">${t("add_title")}</h1>
    <section class="card upload page-enter" id="upload"></section>`;
  drawUpload();
}
