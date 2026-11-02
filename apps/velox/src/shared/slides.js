// Slide files on Toledo (Blackboard Ultra) — pure functions (unit-tested in test/).

import { parseCourseTitle, sanitizeFilename } from "./filename.js";

const EXTENSION = /\.(pdf|pptx)$/i;

// What a file row is, from its aria-label ("PDF, Slides Hoofdstuk 2") or, when
// Toledo labels it differently, from the extension in its title. Verbatim reads
// PDF and PPTX; anything else gets no button.
export function slideType(label, title) {
  if (/^pdf\b/i.test(label || "")) return "pdf";
  if (/^(?:microsoft\s+)?(?:pptx|powerpoint)\b/i.test(label || "")) return "pptx";
  return EXTENSION.exec(String(title || "").trim())?.[1].toLowerCase() ?? null;
}

// "Slides H1.pdf" and "Slides H1" both become "Slides H1.pdf".
export function slideFilename(title, type) {
  return `${sanitizeFilename(
    String(title || "")
      .trim()
      .replace(EXTENSION, ""),
  )}.${type}`;
}

// ".../ultra/courses/_1_1/file/_12_1?courseId=_1_1" → "_12_1"
export function slideContentId(href) {
  return /\/file\/(_\d+_\d+)/.exec(String(href || ""))?.[1] ?? null;
}

// The course code from page headings: "Digitale signaalverwerking [H01L6a]".
export function courseCodeFrom(texts) {
  for (const text of texts) {
    const parsed = parseCourseTitle(text);
    if (parsed) return parsed.code;
  }
  return null;
}

// Only Toledo's own file store, on the site the button was on.
export function isSlideUrl(url, pageUrl) {
  try {
    const file = new URL(url);
    return file.origin === new URL(pageUrl).origin && file.pathname.startsWith("/bbcswebdav/");
  } catch {
    return false;
  }
}
