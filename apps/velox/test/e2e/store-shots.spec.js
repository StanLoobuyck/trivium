// Screenshots for the Edge Add-ons listing (1280×800). The real Velox build on the test page, dressed up:
// a neutral demo slide instead of the test card, a light Toledo-like page, no test hints. No personal data.
// Only on request: STORE_SHOTS=1 npx playwright test store-shots  →  store/edge/screenshots/*.png

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect, openLecture, openPopupFor } from "./fixtures.js";

const ROOT = join(import.meta.dirname, "..", "..");
const OUT = join(ROOT, "store", "edge", "screenshots");
const COURSE = { en: "Introduction to Law", nl: "Inleiding tot het recht" };
const SLIDE = {
  en: ["Lecture 2", "Sources of law", ["Legislation", "Case law", "Custom", "Legal doctrine"]],
  nl: ["Les 2", "Bronnen van het recht", ["Wetgeving", "Rechtspraak", "Gewoonte", "Rechtsleer"]],
};

test.skip(!process.env.STORE_SHOTS, "only for the store listing (STORE_SHOTS=1)");

// A 2-minute "lecture": one slide, rendered by the browser and turned into an mp4 by ffmpeg.
async function slideVideo(context, lang, dir) {
  const mp4 = join(dir, `slide-${lang}.mp4`);
  if (existsSync(mp4)) return mp4;
  const [kicker, title, points] = SLIDE[lang];
  const page = await context.newPage();
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.setContent(`<body style="margin:0;width:1280px;height:720px;background:#fff;font-family:Inter,system-ui,sans-serif;
    display:flex;flex-direction:column;justify-content:center;padding:0 120px;box-sizing:border-box;color:#1d1d1f">
    <div style="color:#0066d6;font-size:28px;font-weight:600">${COURSE[lang]} · ${kicker}</div>
    <h1 style="font-size:64px;margin:16px 0 40px">${title}</h1>
    <ul style="font-size:36px;line-height:1.7;margin:0;padding-left:40px">${points.map((p) => `<li>${p}</li>`).join("")}</ul>
    <div style="position:absolute;bottom:40px;right:60px;width:120px;height:6px;background:#0066d6;border-radius:3px"></div></body>`);
  const png = join(dir, `slide-${lang}.png`);
  await page.screenshot({ path: png });
  await page.close();
  execFileSync("ffmpeg", [
    "-loglevel",
    "error",
    "-y",
    "-loop",
    "1",
    "-i",
    png,
    "-t",
    "120",
    "-r",
    "5",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    mp4,
  ]);
  return mp4;
}

// The test page, made to look like a lecture page: light, the player large, no test hints.
async function dressUp(context, lang, video) {
  const iframe = readFileSync(join(ROOT, "test", "fixtures", "iframe.html"), "utf8")
    .replace(/Velox Testvak \[T01E5T\] • ULTRA-TEST/g, `${COURSE[lang]} [V00A1A] • 2026-27`)
    .replace(/Velox Testvak/g, COURSE[lang])
    .replace(/Lesopnames/g, lang === "nl" ? "Lesopnames" : "Recordings")
    .replace(
      "</head>",
      `<style>
      body { background: #f2f2f7 !important; color: #1d1d1f !important; padding: 32px 40px !important; }
      .crumbs, .crumbs a { color: #0066d6 !important; max-width: none !important; }
      iframe { max-width: none !important; width: 100% !important; border-radius: 12px; }
      body > p, .hint { display: none !important; }
    </style></head>`,
    );
  await context.route(/\/iframe\.html/, (route) => route.fulfill({ contentType: "text/html", body: iframe }));
  await context.route(/\/media\/lecture\.mp4$/, (route) =>
    route.fulfill({ path: video, contentType: "video/mp4" }),
  );
}

for (const lang of ["en", "nl"]) {
  test(`store screenshots (${lang})`, async ({ context, extensionId, serviceWorker }, testInfo) => {
    test.setTimeout(120_000);
    mkdirSync(OUT, { recursive: true });
    const video = await slideVideo(context, lang, testInfo.outputDir);
    await dressUp(context, lang, video);
    await serviceWorker.evaluate((l) => chrome.storage.sync.set({ language: l }), lang);
    const title =
      lang === "nl" ? "Les 2 (2026-09-24): Bronnen van het recht" : "Lecture 2 (2026-09-24): Sources of law";
    const { page, frame } = await openLecture(context, { slow: true, title });
    await frame.evaluate(() => {
      const v = document.querySelector("video");
      v.currentTime = 41;
      return v.play();
    });
    await page.mouse.click(5, 5); // outside the player, like a user who clicked the page

    // 1. Speed: two presses on ] → 1.5× with the overlay
    // The overlay fades in for 0.2 s and stays 1.1 s (content.js): the picture at 0.5 s shows it fully.
    await page.keyboard.press("BracketRight");
    await page.keyboard.press("BracketRight");
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(OUT, `1-speed-${lang}.png`) });
    expect(await frame.evaluate(() => document.querySelector("#velox-osd").className)).toBe("velox-bump");
    await expect(frame.locator(".velox-osd-label")).toHaveText(lang === "nl" ? "1,5×" : "1.5×");

    // 2. The shortcut sheet
    await page.keyboard.press("Shift+Slash");
    await expect(frame.locator(".velox-sheet")).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: join(OUT, `2-shortcuts-${lang}.png`) });
    await page.keyboard.press("Escape");

    // 3. Downloading (the slow server keeps it busy long enough)
    await frame.locator(".ss-dl-main").click();
    await expect(frame.locator("#velox-download")).toHaveAttribute("data-mode", "busy");
    await expect(frame.locator(".ss-dl-meta")).toHaveText(/(kB|MB)\/s/);
    await expect(frame.locator(".ss-dl-main-label")).toHaveText(/\d+%/);
    await page.screenshot({ path: join(OUT, `3-download-${lang}.png`) });

    // 4. The popup (rendered on its own; then put over the dimmed page with ImageMagick)
    const popup = await openPopupFor(context, extensionId, serviceWorker, page.url());
    await popup.setViewportSize({ width: 360, height: 600 });
    await expect(popup.locator("#speed-value")).toBeVisible();
    const box = await popup.evaluate(() => {
      const r = document.body.getBoundingClientRect();
      return { width: Math.ceil(r.width), height: Math.ceil(document.documentElement.scrollHeight) };
    });
    await popup.setViewportSize(box);
    await popup.screenshot({ path: join(testInfo.outputDir, `popup-${lang}.png`) });
    await page.bringToFront();
    await page.screenshot({ path: join(testInfo.outputDir, `page-${lang}.png`) });
    execFileSync("magick", [
      join(testInfo.outputDir, `page-${lang}.png`),
      "-fill",
      "rgba(0,0,0,0.25)",
      "-draw",
      "rectangle 0,0 1280,800",
      "(",
      join(testInfo.outputDir, `popup-${lang}.png`),
      "(",
      "+clone",
      "-background",
      "black",
      "-shadow",
      "40x12+0+8",
      ")",
      "+swap",
      "-background",
      "none",
      "-layers",
      "merge",
      "+repage",
      ")",
      "-geometry",
      "+880+24",
      "-composite",
      join(OUT, `4-popup-${lang}.png`),
    ]);
  });
}
