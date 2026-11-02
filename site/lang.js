// Taal van de Trivium-pagina's: browsertaal, of wat de bezoeker koos met de NL/EN-knop.
// apply(lang) zet de teksten; blokken met data-lang="nl|en" worden vanzelf getoond of verborgen.
export function initLang(apply = () => {}) {
  function set(lang, remember) {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-lang]").forEach((el) => { el.hidden = el.dataset.lang !== lang; });
    document.querySelectorAll("[data-set-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.setLang === lang)));
    apply(lang);
    if (remember) try { localStorage.setItem("trivium-lang", lang); } catch {}
  }
  let saved = null;
  try { saved = localStorage.getItem("trivium-lang"); } catch {}
  set(saved || ((navigator.language || "nl").toLowerCase().startsWith("nl") ? "nl" : "en"), false);
  document.querySelectorAll("[data-set-lang]").forEach((b) => b.addEventListener("click", () => set(b.dataset.setLang, true)));
}
