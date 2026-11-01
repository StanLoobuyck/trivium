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

// Naar beneden vegen sluit de sheet, zoals op iOS: alleen als ze bovenaan staat en niet vanuit een tekstveld.
function initSheetDrag() {
  const sheet = $("#sheet");
  const scrim = $("#scrim");
  let drag = null;
  const release = () => {
    sheet.classList.remove("is-dragging");
    scrim.classList.remove("is-dragging");
    sheet.style.transform = "";
    scrim.style.opacity = "";
  };
  sheet.addEventListener("touchstart", (e) => {
    if (e.touches.length !== 1 || e.target.closest("textarea, select")) return;
    const { clientX: x, clientY: y } = e.touches[0];
    drag = { x, y, dy: 0, time: e.timeStamp, active: false };
  }, { passive: true });
  sheet.addEventListener("touchmove", (e) => {
    if (!drag) return;
    const dx = e.touches[0].clientX - drag.x;
    const dy = e.touches[0].clientY - drag.y;
    if (!drag.active) {
      if (Math.abs(dx) > Math.abs(dy) || dy <= 4 || sheet.scrollTop > 0) {
        if (Math.abs(dx) + Math.abs(dy) > 8) drag = null;
        return;
      }
      drag.active = true;
      sheet.classList.add("is-dragging");
      scrim.classList.add("is-dragging");
    }
    e.preventDefault();
    drag.dy = Math.max(0, dy);
    sheet.style.transform = `translateY(${drag.dy}px)`;
    scrim.style.opacity = String(1 - Math.min(1, drag.dy / sheet.offsetHeight));
  }, { passive: false });
  const end = (e) => {
    if (!drag?.active) { drag = null; return; }
    const { dy, time } = drag;
    drag = null;
    const fast = dy / Math.max(1, e.timeStamp - time) > 0.5;
    if (dy > Math.min(120, sheet.offsetHeight / 3) || (fast && dy > 30)) closeSheet();
    release();
  };
  sheet.addEventListener("touchend", end);
  sheet.addEventListener("touchcancel", end);
}

export function initSheet() {
  initSheetDrag();
  $("#scrim").addEventListener("click", closeSheet);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("#sheet-root").classList.contains("is-open")) closeSheet();
  });
}
