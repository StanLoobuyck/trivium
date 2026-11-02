import { test, expect, openLecture, playerFrame } from "./fixtures.js";

// Records the file names Velox asks the browser to save. (Playwright
// saves downloads under random names, so the real file name isn't visible.)
async function recordDownloads(serviceWorker) {
  await serviceWorker.evaluate(() => {
    const original = chrome.downloads.download.bind(chrome.downloads);
    globalThis.__requested = [];
    chrome.downloads.download = (options) => {
      globalThis.__requested.push(options.filename);
      return original(options);
    };
  });
  return {
    names: () => serviceWorker.evaluate(() => globalThis.__requested),
    completed: () =>
      serviceWorker.evaluate(async () =>
        (await chrome.downloads.search({ state: "complete" })).map((d) => ({
          mime: d.mime,
          size: d.fileSize,
        })),
      ),
  };
}

test("download from the player: progress ring, collapse, Saved, correct .mp4", async ({
  context,
  serviceWorker,
}, testInfo) => {
  const downloads = await recordDownloads(serviceWorker);
  const { page, frame } = await openLecture(context, { slow: true });
  const control = frame.locator("#velox-download");

  await frame.locator(".ss-dl-main").click();
  await expect(control).toHaveAttribute("data-mode", "busy");
  await expect(frame.locator(".ss-dl-main-label")).toHaveText(/Downloading \d+%/);
  await expect(frame.locator(".ss-dl-meta")).toHaveText(/(kB|MB)\/s/);
  await testInfo.attach("download-busy", { body: await page.screenshot(), contentType: "image/png" });

  // Collapsed while downloading: the round button's ring shows progress.
  await frame.locator(".ss-dl-side").click();
  await expect(frame.locator(".ss-dl-orb")).toBeVisible();
  await expect(frame.locator(".ss-dl-orb-ring")).toBeVisible();
  await frame.locator(".ss-dl-orb").click();

  await expect(control).toHaveAttribute("data-mode", "done", { timeout: 30_000 });
  await expect(frame.locator(".ss-dl-main-label")).toHaveText("Saved");
  expect(await downloads.names()).toEqual(["Velox Testvak - Les 2 (2026-09-24) - e2e.mp4"]);
  // "Saved" means the browser started saving; the file may need a moment more.
  await expect.poll(async () => (await downloads.completed()).length).toBe(1);
  const [file] = await downloads.completed();
  expect(file.mime).toBe("video/mp4");
  expect(file.size).toBeGreaterThan(1_000_000);
});

test("cancelling a download stops it and saves nothing", async ({ context, serviceWorker }) => {
  const downloads = await recordDownloads(serviceWorker);
  const { frame } = await openLecture(context, { slow: true });
  await frame.locator(".ss-dl-main").click();
  await expect(frame.locator("#velox-download")).toHaveAttribute("data-mode", "busy");
  await frame.getByRole("button", { name: "Cancel download" }).click();
  await expect(frame.locator("#velox-download")).toHaveAttribute("data-mode", "idle");
  await frame.waitForTimeout(1500);
  expect(await downloads.names()).toEqual([]);
});

test("the collapsed state is remembered", async ({ context }) => {
  const { page, frame } = await openLecture(context);
  await frame.getByRole("button", { name: "Minimize" }).click();
  await expect(frame.locator(".ss-dl-orb")).toBeVisible();
  await page.reload();
  const again = await playerFrame(page);
  await expect(again.locator(".ss-dl-orb")).toBeVisible({ timeout: 15_000 });
  await expect(again.locator(".ss-dl-pill")).toBeHidden();
});

// A player that switches lectures without reloading: the download follows the
// new lecture, while the playlists the player loads for the current one don't
// replace its (master) playlist.
test("a lecture switch inside the player moves the download to the new lecture", async ({
  context,
  serviceWorker,
}) => {
  const { frame } = await openLecture(context);
  const storedUrl = () =>
    serviceWorker.evaluate(async () => {
      const stored = await chrome.storage.session.get(null);
      return Object.entries(stored).find(([key]) => key.startsWith("tab:"))?.[1].url;
    });
  await expect.poll(storedUrl).toMatch(/\/media\/hls\/index\.m3u8$/);

  await frame.evaluate(() => fetch("media/hls/index.m3u8?entryId=0_second"));
  await expect.poll(storedUrl).toMatch(/entryId=0_second$/);

  // Same entry again (a variant playlist): stays on the first URL of that lecture.
  await frame.evaluate(() => fetch("media/hls/index.m3u8?entryId=0_second&variant=720"));
  await frame.waitForTimeout(500);
  expect(await storedUrl()).toMatch(/entryId=0_second$/);
});

// A recording with two pictures (slides + webcam): two entries playing at once. The webcam is a second
// picture, not another lecture; it is only downloaded for Verbatim, which puts both side by side.
async function addSecondPicture(frame) {
  await frame.evaluate(async () => {
    const webcam = document.createElement("video");
    webcam.muted = true;
    document.querySelector(".player").append(webcam);
    await fetch("media/hls/index.m3u8?entryId=0_webcam");
  });
}

const storedStreams = (serviceWorker) =>
  serviceWorker.evaluate(async () => {
    const stored = await chrome.storage.session.get(null);
    const state = Object.entries(stored).find(([key]) => key.startsWith("tab:"))?.[1];
    return { url: state?.url, companionUrl: state?.companionUrl };
  });

test("two pictures: without Verbatim only the slides are saved", async ({ context, serviceWorker }) => {
  const downloads = await recordDownloads(serviceWorker);
  const { frame } = await openLecture(context);
  await addSecondPicture(frame);
  await expect
    .poll(() => storedStreams(serviceWorker))
    .toEqual({
      url: expect.stringMatching(/\/media\/hls\/index\.m3u8$/),
      companionUrl: expect.stringMatching(/entryId=0_webcam$/),
    });

  await frame.locator(".ss-dl-main").click();
  await expect(frame.locator("#velox-download")).toHaveAttribute("data-mode", "done", { timeout: 30_000 });
  expect(await downloads.names()).toEqual(["Velox Testvak - Les 2 (2026-09-24) - e2e.mp4"]);
});

test("two pictures with Verbatim: webcam first, then the slides, one progress bar", async ({
  context,
  serviceWorker,
}) => {
  await serviceWorker.evaluate(() => chrome.storage.sync.set({ downloadsToVerbatim: true }));
  const downloads = await recordDownloads(serviceWorker);
  const { frame } = await openLecture(context, { slow: true });
  await addSecondPicture(frame);
  await expect.poll(async () => (await storedStreams(serviceWorker)).companionUrl).toMatch(/0_webcam$/);

  await frame.locator(".ss-dl-main").click();
  // The first file finishing is halfway, not done.
  await expect.poll(async () => (await downloads.names()).length, { timeout: 30_000 }).toBe(1);
  await expect(frame.locator("#velox-download")).toHaveAttribute("data-mode", "busy");
  await expect(frame.locator("#velox-download")).toHaveAttribute("data-mode", "done", { timeout: 60_000 });
  expect(await downloads.names()).toEqual([
    "Verbatim/T01E5T/Velox Testvak - Les 2 (2026-09-24) - e2e.webcam.mp4",
    "Verbatim/T01E5T/Velox Testvak - Les 2 (2026-09-24) - e2e.mp4",
  ]);
});
