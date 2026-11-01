// Small UI building blocks shared by the screens: toasts, flicker-free repaint, polling, the top-bar title,
// inline rename fields and the card menu.
import { $, $$ } from "./dom.js";
import { S } from "./state.js";
import { drawLibrary } from "../screens/library.js";

export function toast(msg, bad = false) {
  const el = document.createElement("div");
  el.className = "toast" + (bad ? " bad" : "");
  el.textContent = msg;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), bad ? 7000 : 3500);
}

// Polled parts are only rebuilt when their HTML changed: rebuilding unchanged DOM every few seconds made the
// page flicker (hover states, focus and animations reset). Returns false when nothing changed.
export function paint(el, html) {
  if (el._html === html) return false;
  el._html = html;
  el.innerHTML = html;
  return true;
}

export function setBarTitle(text, show = false) {
  const el = $("#bar-title");
  el.textContent = text;
  el.classList.toggle("show", !!text && show);
  el.onclick = () => window.scrollTo({ top: 0, behavior: "smooth" });
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
