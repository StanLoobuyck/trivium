// Swipe naar rechts = bekeken, swipe naar links of lang drukken = meer opties.
const THRESHOLD = 72;
const LONG_PRESS = 500;

// Na een swipe of lang drukken kan de browser nog een klik sturen; die mag niets openen.
let ignoreClicksUntil = 0;
export const clickIgnored = () => performance.now() < ignoreClicksUntil;
const ignoreClick = () => { ignoreClicksUntil = performance.now() + 400; };

export function initGestures(root, { onTick, onOptions }) {
  let active = null;
  let pressed = false;

  const reset = () => {
    if (!active) return;
    clearTimeout(active.timer);
    active.row.style.transform = "";
    active.row.classList.remove("is-dragging");
    active = null;
  };

  root.addEventListener("pointerdown", (e) => {
    const swipe = e.target.closest("[data-swipe]");
    if (!swipe || e.pointerType === "mouse" || e.target.closest(".check")) return;
    const row = swipe.querySelector(".row");
    active = { id: swipe.dataset.swipe, row, x: e.clientX, y: e.clientY, dx: 0, moved: false };
    active.timer = setTimeout(() => {
      if (active && !active.moved) {
        const { id } = active;
        pressed = true;
        reset();
        onOptions(id);
      }
    }, LONG_PRESS);
  });

  root.addEventListener("pointermove", (e) => {
    if (!active) return;
    const dx = e.clientX - active.x;
    const dy = e.clientY - active.y;
    if (!active.moved && Math.abs(dx) + Math.abs(dy) > 8) {
      clearTimeout(active.timer);
      if (Math.abs(dy) > Math.abs(dx)) { reset(); return; }
      active.moved = true;
      active.row.classList.add("is-dragging");
    }
    if (active.moved) {
      active.dx = dx;
      active.row.style.transform = `translateX(${dx}px)`;
    }
  });

  const finish = () => {
    if (pressed) { pressed = false; ignoreClick(); }
    if (!active) return;
    const { dx, id, moved } = active;
    reset();
    if (!moved) return;
    ignoreClick();
    if (dx > THRESHOLD) onTick(id);
    else if (dx < -THRESHOLD) onOptions(id);
  };
  root.addEventListener("pointerup", finish);
  root.addEventListener("pointercancel", reset);
}
