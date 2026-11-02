// Sneltoetsen op de laptop: J/K bewegen, X of spatie vinkt af, N voegt toe, 1-9 kiest een vak, Z maakt ongedaan.
import { $, $$ } from "./dom.js";

export function initShortcuts({ onAdd, onCourse }) {
  const rows = () => $$(".check[data-tick]");
  const focusRow = (index) => {
    const list = rows();
    if (!list.length) return;
    list[Math.max(0, Math.min(index, list.length - 1))].focus();
  };

  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.closest("input, textarea, select") || $("#sheet-root").classList.contains("is-open")) return;
    const index = rows().indexOf(document.activeElement);
    const key = e.key.toLowerCase();

    if (key === "j") focusRow(index + 1);
    else if (key === "k") focusRow(index < 0 ? 0 : index - 1);
    else if (key === "x" || (key === " " && index >= 0)) {
      if (index < 0) return;
      e.preventDefault();
      rows()[index].click();
      focusRow(index);
    } else if (key === "n") { e.preventDefault(); onAdd(); }
    else if (key === "z") $("#toast.is-open button")?.click();
    else if (/^[1-9]$/.test(key)) onCourse(+key - 1);
  });
}

// Staafjes: met de muis erover of je vinger erop (ook slepend) zie je welke week het is.
export function initChart(root) {
  const show = (x, y) => {
    const slot = document.elementFromPoint(x, y)?.closest(".bar-slot");
    if (!slot) return;
    $$(".bar-slot.is-active", root).forEach((s) => s.classList.remove("is-active"));
    slot.classList.add("is-active");
    $("#bars-readout", root).textContent = slot.dataset.tip;
  };
  root.addEventListener("pointerdown", (e) => { if (e.target.closest(".bars")) show(e.clientX, e.clientY); });
  root.addEventListener("pointermove", (e) => { if (e.target.closest(".bars")) show(e.clientX, e.clientY); });
}
