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

// Het grote getal telt mee en de balk schuift van de vorige naar de nieuwe stand.
let shown = null;

export function playHero(animate = true) {
  const number = document.querySelector(".hero-number");
  const bar = document.querySelector(".hero .progress > span");
  if (!number) { shown = null; return; }
  const target = +number.textContent;
  const value = bar.style.getPropertyValue("--value");
  const from = shown;
  shown = { target, value };
  if (!animate || !from || from.target === target || matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  bar.style.setProperty("--value", from.value);
  requestAnimationFrame(() => requestAnimationFrame(() => bar.style.setProperty("--value", value)));
  number.classList.add("is-changing");
  const frames = 12;
  let frame = 0;
  const step = () => {
    frame += 1;
    if (!number.isConnected) return;
    number.textContent = Math.round(from.target + ((target - from.target) * frame) / frames);
    if (frame < frames) requestAnimationFrame(step);
  };
  step();
}
