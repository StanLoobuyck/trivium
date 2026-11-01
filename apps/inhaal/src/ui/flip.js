// FLIP: lijsten bewegen naar hun nieuwe plek in plaats van te springen.
export function captureRects() {
  return new Map([...document.querySelectorAll("[data-flip]")].map((e) => [e.dataset.flip, e.getBoundingClientRect().top]));
}

export function playFlip(before) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const easing = getComputedStyle(document.documentElement).getPropertyValue("--ease-spring");
  for (const element of document.querySelectorAll("[data-flip]")) {
    const top = before.get(element.dataset.flip);
    if (top === undefined) continue;
    const delta = top - element.getBoundingClientRect().top;
    if (delta) element.animate([{ transform: `translateY(${delta}px)` }, { transform: "none" }], { duration: 300, easing });
  }
}
