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
