// The "save to the course folder" button next to PDF and PPTX files on Toledo.
// Toledo renders rows without page loads and only while their folder is open,
// so a page observer adds the buttons. Row: the file link, plus Ally's hidden
// link with the real file address (Toledo adds it a little later).

import { courseCodeFrom, slideContentId, slideType } from "../shared/slides.js";
import { getSavedSlides } from "../shared/storage.js";
import { t } from "../shared/i18n.js";
import { icon } from "./download-control.js";

const FILE_LINKS = 'a[aria-label][href*="/ultra/courses/"][href*="/file/"]';
const SCAN_DELAY_MS = 300;
const ICON_FOR = { idle: "download", busy: "download", saved: "done", failed: "failed" };

export function createSlideButtons() {
  let observer = null;
  let timer = null;

  function setState(button, state, code, title) {
    button.dataset.state = state;
    button.disabled = state === "busy";
    button.replaceChildren(icon(ICON_FOR[state]));
    const key = { idle: "slideSave", busy: "slideSaving", saved: "slideSaved", failed: "slideFailed" }[state];
    const text = t(key, { code });
    button.title = text;
    button.setAttribute("aria-label", `${text}: ${title}`);
  }

  function addButton(link, code, saved) {
    const id = slideContentId(link.href);
    const title = link.textContent.trim();
    const type = slideType(link.getAttribute("aria-label"), title);
    if (!id || !type) return;
    const fileUrl = document
      .querySelector(`[data-ally-content-id="${id}"]`)
      ?.getAttribute("data-ally-file-preview-url");
    if (!fileUrl) return;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "swiftskip-slide";
    setState(button, saved.has(id) ? "saved" : "idle", code, title);
    button.addEventListener("click", (event) => {
      // The row around it opens the file.
      event.preventDefault();
      event.stopPropagation();
      setState(button, "busy", code, title);
      // Against the site itself, not the page's base: on Toledo a relative address ended up on its CDN.
      const url = new URL(fileUrl, window.location.origin).href;
      chrome.runtime.sendMessage({ action: "saveSlide", url, id, title, type, code }, (reply) => {
        void chrome.runtime.lastError;
        setState(button, reply?.ok ? "saved" : "failed", code, title);
      });
    });
    link.after(button);
  }

  async function scan() {
    timer = null;
    if (!observer) return;
    const links = [...document.querySelectorAll(FILE_LINKS)].filter(
      (link) => !link.nextElementSibling?.matches(".swiftskip-slide"),
    );
    if (!links.length) return;
    const headings = [...document.querySelectorAll("h1, nav a")].map((node) => node.textContent);
    const code = courseCodeFrom(headings);
    if (!code) return;
    const saved = await getSavedSlides(code);
    if (!observer) return;
    for (const link of links) {
      if (!link.nextElementSibling?.matches(".swiftskip-slide")) addButton(link, code, saved);
    }
  }

  const schedule = () => {
    if (!timer) timer = setTimeout(scan, SCAN_DELAY_MS);
  };

  return {
    // On while downloads go to Verbatim; off leaves Toledo untouched.
    update(active) {
      if (active && !observer) {
        observer = new MutationObserver(schedule);
        observer.observe(document.body, { childList: true, subtree: true });
        schedule();
      } else if (!active && observer) {
        observer.disconnect();
        observer = null;
        clearTimeout(timer);
        timer = null;
        for (const button of document.querySelectorAll(".swiftskip-slide")) button.remove();
      }
    },
  };
}
