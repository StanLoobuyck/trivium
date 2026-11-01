// Light / dark / system for SwiftSkip's own pages, the same html[data-theme] as Inhaal. Settings load
// asynchronously, so the choice is also kept in localStorage: that keeps a dark popup from flashing light.

const KEY = "swiftskip-theme";

function set(choice) {
  if (choice === "light" || choice === "dark") document.documentElement.dataset.theme = choice;
  else delete document.documentElement.dataset.theme;
}

export function applyTheme(choice) {
  set(choice);
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    /* blocked storage: settings still apply it, a moment later */
  }
}

try {
  set(localStorage.getItem(KEY));
} catch {
  /* see above */
}
