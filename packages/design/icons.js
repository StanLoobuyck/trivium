// Gedeelde iconen op een raster van 24 px. icon("check") geeft een <svg>-string met klasse .icon.
const paths = {
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chevron: '<path d="M9 5l7 7-7 7"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  undo: '<path d="M8 6L3.5 10.5 8 15"/><path d="M4 10.5h10a5.5 5.5 0 010 11h-3"/>',
  overview: '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.5l2.8 2.8L16 9.5"/>',
  book: '<path d="M4.5 5.5A2.5 2.5 0 017 3h12.5v15H7a2.5 2.5 0 00-2.5 2.5z"/><path d="M4.5 20.5A2.5 2.5 0 007 23"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>',
  more: '<circle cx="5.5" cy="12" r="0.8"/><circle cx="12" cy="12" r="0.8"/><circle cx="18.5" cy="12" r="0.8"/>',
};

export function icon(name) {
  if (!paths[name]) throw new Error(`Onbekend icoon: ${name}`);
  return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
}

export const iconNames = Object.keys(paths);
