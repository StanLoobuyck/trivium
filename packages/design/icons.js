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
  download: '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
  folder: '<path d="M3.5 7a2 2 0 012-2h4l2 2.5h7a2 2 0 012 2V18a2 2 0 01-2 2h-13a2 2 0 01-2-2z"/>',
  archive: '<rect x="3.5" y="4.5" width="17" height="5" rx="1.5"/><path d="M5 9.5V18a2 2 0 002 2h10a2 2 0 002-2V9.5M10 13.5h4"/>',
  keyboard: '<rect x="3" y="6" width="18" height="12" rx="2.5"/><path d="M7 10h.01M11 10h.01M15 10h.01M7.5 14h9"/>',
  link: '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.5 3.5 5.3 3.5 8.5s-1 6-3.5 8.5c-2.5-2.5-3.5-5.3-3.5-8.5s1-6 3.5-8.5z"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
  more: '<circle cx="5.5" cy="12" r="0.8"/><circle cx="12" cy="12" r="0.8"/><circle cx="18.5" cy="12" r="0.8"/>',
};

export function icon(name) {
  if (!paths[name]) throw new Error(`Onbekend icoon: ${name}`);
  return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
}

export const iconNames = Object.keys(paths);
