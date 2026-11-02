import { enGB, nlBE } from "date-fns/locale";
import { format } from "date-fns";
import nl from "./nl.json";
import en from "./en.json";

const KEY = "sequo-lang";
const read = () => {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
};

export const langChoice = () => read() ?? "auto";

export const lang = () => {
  const choice = read();
  if (choice === "nl" || choice === "en") return choice;
  return navigator.language?.toLowerCase().startsWith("nl") ? "nl" : "en";
};

export function setLang(choice) {
  try {
    if (choice === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    // Privévenster: de keuze geldt dan alleen voor deze sessie niet.
  }
  document.documentElement.lang = lang();
}

const THEME_KEY = "sequo-theme";

export function themeChoice() {
  try {
    return localStorage.getItem(THEME_KEY) ?? "system";
  } catch {
    return "system";
  }
}

export function setTheme(choice) {
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Privévenster: de keuze geldt dan alleen tot je de app sluit.
  }
  if (choice === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
}

export function t(key, vars = {}) {
  const text = { nl, en }[lang()][key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? "");
}

const locale = () => (lang() === "nl" ? nlBE : enGB);

// Nederlands: twee letters ("di 13 okt"); Engels: drie ("Tue 13 Oct").
const weekday = () => (lang() === "nl" ? "EEEEEE" : "EEE");
export const shortDate = (date) => format(date, `${weekday()} d MMM`, { locale: locale() }).replace(/\./g, "");
export const chipDate = (date) => format(date, `${weekday()} d/MM`, { locale: locale() }).replace(/\./g, "");
export const timeOf = (date) => format(date, "HH:mm");

export function duration(minutes) {
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  const pad = String(rest).padStart(2, "0");
  return lang() === "nl" ? `${hours}u ${pad}` : `${hours}h ${pad}`;
}
