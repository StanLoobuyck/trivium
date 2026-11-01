// Small UI building blocks shared by the screens: toasts, flicker-free repaint, polling, the top-bar title,
// inline rename fields and the card menu.
import { $, $$ } from "./dom.js";
import { esc } from "./format.js";
import { S } from "./state.js";
import { drawLibrary } from "../screens/library.js";

let toastTimer = null;
export function toast(msg, bad = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("is-open");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-open"), bad ? 7000 : 3500);
}

// Laptop: the page scrolls inside #scroller (as in Inhaal). Narrow: the document itself scrolls.
export function scroller() {
  const el = $("#scroller");
  return getComputedStyle(el).overflowY === "auto" ? el : document.scrollingElement;
}

// Polled parts are only rebuilt when their HTML changed: rebuilding unchanged DOM every few seconds made the
// page flicker (hover states, focus and animations reset). Returns false when nothing changed.
export function paint(el, html) {
  if (el._html === html) return false;
  el._html = html;
  el.innerHTML = html;
  return true;
}

// Lecture page: title + one line under it in the bar above the page.
export function setBarTitle(title = "", sub = "") {
  $("#bar-title").innerHTML = title ? `<h1 class="editable" id="lec-title" title="${t("rename")}">${esc(title)}</h1><p class="label">${esc(sub)}</p>` : "";
}

// Same three choices as Inhaal; "system" removes the override so the OS decides.
export const themeChoice = () => document.documentElement.dataset.theme || "system";
export function setTheme(choice) {
  if (choice === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
  try { if (choice === "system") localStorage.removeItem("lt-theme"); else localStorage.setItem("lt-theme", choice); }
  catch { /* private window: just not remembered */ }
}

let pollTimer = null;
export function poll(fn, ms) {
  clearInterval(pollTimer);
  pollTimer = setInterval(() => { if (!document.hidden) fn(); }, ms);
}
export const stopPoll = () => clearInterval(pollTimer);

export function closeMenus() { $$(".menu").forEach((m) => m.remove()); }

// Swap an element for a text field; Enter or leaving the field saves, Escape cancels. onSave may throw.
// `after` runs once the element is back (default: rebuild the library, which may show the new name).
export function inlineEdit(el, value, onSave, placeholder = "", after = null) {
  S.editing = true;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "inline-edit";
  input.value = value;
  input.placeholder = placeholder;
  input.style.fontSize = getComputedStyle(el).fontSize;  // a title stays title-sized while editing
  el.replaceWith(input);
  input.focus();
  input.select();
  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const v = input.value.trim();
    if (save && v && v !== value) {
      try { await onSave(v); } catch (e) { toast(e.message, true); }
    }
    input.replaceWith(el);
    S.editing = false;
    if (after) return after();
    const wrap = $("#lib-wrap");
    if (wrap) { wrap._html = null; drawLibrary(); }
  };
  input.addEventListener("click", (e) => e.stopPropagation());
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") finish(true);
    if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
}
