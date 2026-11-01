// Lecture Transcriber UI entry point (ES modules, no build step). Texts come from i18n.js (t(), LANG, setLang),
// loaded before this as a classic script. Structure: core/ (dom, api, state, ui, router), shared/ (used by
// several screens), screens/ (one module per page).
import { api } from "./core/api.js";
import { $$ } from "./core/dom.js";
import { route } from "./core/router.js";
import { S } from "./core/state.js";
import { closeMenus } from "./core/ui.js";

function translateStatic() {
  $$("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
}

document.addEventListener("click", (e) => { if (!e.target.closest(".menu") && !e.target.closest("[data-menu]")) closeMenus(); });
document.addEventListener("scroll", closeMenus, { passive: true, capture: true });  // pop-up menus are placed once, by the button
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenus(); });

setLang(LANG);
translateStatic();
try { S.courses = await api("/api/courses"); } catch { S.courses = []; }
route();
