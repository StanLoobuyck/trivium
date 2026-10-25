// Lecture Transcriber UI entry point (ES modules, no build step). Texts come from i18n.js (t(), LANG, setLang),
// loaded before this as a classic script. Structure: core/ (dom, api, state, ui, router), shared/ (used by
// several screens), screens/ (one module per page).
import { api } from "./core/api.js";
import { $, $$ } from "./core/dom.js";
import { route } from "./core/router.js";
import { S } from "./core/state.js";
import { closeMenus } from "./core/ui.js";

function translateStatic() {
  $$("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
  $$("[data-t-title]").forEach((el) => { el.title = el.ariaLabel = t(el.dataset.tTitle); });
  $$(".lang button").forEach((b) => b.classList.toggle("on", b.dataset.lang === LANG));
}
$$(".lang button").forEach((b) => b.addEventListener("click", () => { setLang(b.dataset.lang); translateStatic(); route(); }));

// theme: follows the system until the top-bar button picks one; the choice is remembered (index.html applies it
// before first paint, so a dark-mode user never sees a white flash)
$("#theme-btn").addEventListener("click", () => {
  const sysDark = matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = (document.documentElement.dataset.theme || (sysDark ? "dark" : "light")) === "dark";
  const next = dark ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("lt-theme", next); } catch { /* private window: just not remembered */ }
});

document.addEventListener("click", (e) => { if (!e.target.closest(".menu") && !e.target.closest("[data-menu]")) closeMenus(); });
window.addEventListener("scroll", closeMenus, { passive: true });  // pop-up menus are placed once, by the button
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenus(); });

setLang(LANG);
translateStatic();
try { S.courses = await api("/api/courses"); } catch { S.courses = []; }
route();
