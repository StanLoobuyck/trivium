// Text formatting: escaping, timestamps, durations, sizes, dates (LANG comes from i18n.js).
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const parseTs = (x) => String(x).split(":").reduce((acc, v) => acc * 60 + Number(v), 0);
export const fmtTs = (s) => {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(sec).padStart(2, "0")}`;
};
export const fmtDur = (s) => {
  if (!s) return "";
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? `${h}h${String(m).padStart(2, "0")}m` : `${m}m`;
};
export const fmtSize = (b) => (b > 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(b / 1e6))} MB`);
export const locale = () => (LANG === "nl" ? "nl-BE" : "en-GB");
export const fmtDate = (d) => {
  if (!d) return "";
  const dt = new Date(d + "T12:00:00");
  return isNaN(dt) ? d : dt.toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" });
};
export const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay ? d.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleString(locale(), { weekday: "short", hour: "2-digit", minute: "2-digit" });
};
// "1:58" (hours:minutes) for list columns, "7 h 56 min" for totals
export const fmtHm = (s) => {
  if (!s) return "";
  const m = Math.round(s / 60);
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
};
export const fmtLong = (s) => {
  const m = Math.round((s || 0) / 60), h = Math.floor(m / 60);
  return h ? `${h} h ${m % 60} min` : `${m} min`;
};
// "2026-27 S1" → "2026–27 · semester 1"
export const fmtSem = (s) => (s ? `${s.slice(0, 4)}–${s.slice(5, 7)} · ${t("semester")} ${s.slice(-1)}` : "");
