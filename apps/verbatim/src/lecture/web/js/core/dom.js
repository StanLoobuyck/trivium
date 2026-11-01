// DOM helpers. Modules run after the document is parsed, so #view exists.
export const $ = (sel, el = document) => el.querySelector(sel);
export const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
export const view = $("#view");
