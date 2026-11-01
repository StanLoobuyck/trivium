import { t } from "../i18n/index.js";
import { $, esc } from "./dom.js";

let timer;

export function toast(message, undo) {
  const element = $("#toast");
  element.innerHTML = `<span>${esc(message)}</span>${undo ? `<button>${esc(t("undo"))}</button>` : ""}`;
  element.classList.add("is-open");
  clearTimeout(timer);
  const close = () => element.classList.remove("is-open");
  timer = setTimeout(close, 5000);
  element.querySelector("button")?.addEventListener("click", () => { clearTimeout(timer); close(); undo(); });
}

let opener;

export function openSheet(html, label) {
  const root = $("#sheet-root");
  const sheet = $("#sheet");
  if (!root.classList.contains("is-open")) opener = document.activeElement;
  sheet.innerHTML = html;
  sheet.setAttribute("aria-label", label);
  sheet.scrollTop = 0;
  root.classList.add("is-open");
  $("#shell").inert = true;
  sheet.focus();
  return sheet;
}

export function closeSheet() {
  $("#sheet-root").classList.remove("is-open");
  $("#shell").inert = false;
  if (opener?.isConnected) opener.focus();
}

export function initSheet() {
  $("#scrim").addEventListener("click", closeSheet);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("#sheet-root").classList.contains("is-open")) closeSheet();
  });
}
