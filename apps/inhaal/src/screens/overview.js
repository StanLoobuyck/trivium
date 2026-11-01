import { icon } from "@studie/design/icons.js";
import { t } from "../i18n/index.js";

export function renderOverview(root) {
  root.innerHTML = `
    <main class="page">
      <h1 class="large-title">${t("appTitle")}</h1>
      <section class="card empty">
        ${icon("calendar")}
        <h2 class="title">${t("emptyTitle")}</h2>
        <p class="sub">${t("emptyBody")}</p>
      </section>
    </main>`;
}
