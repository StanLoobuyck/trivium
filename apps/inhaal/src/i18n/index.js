import nl from "./nl.json";
import en from "./en.json";

export const lang = navigator.language?.toLowerCase().startsWith("nl") ? "nl" : "en";

const strings = { nl, en }[lang];

export const t = (key) => strings[key] ?? key;
