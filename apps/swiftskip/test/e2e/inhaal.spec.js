import { test, expect, openLecture, video, BASE } from "./fixtures.js";

const ADDRESS = `${BASE}/inhaal-test/`;
const options = (id, address = ADDRESS) =>
  `chrome-extension://${id}/options.html#link=${encodeURIComponent(address)}`;
const queue = (worker) =>
  worker.evaluate(async () => (await chrome.storage.local.get("inhaalQueue")).inhaalQueue || []);

async function link(context, extensionId) {
  const settings = await context.newPage();
  await settings.goto(options(extensionId));
  await settings.getByRole("button", { name: "Link", exact: true }).click();
  await expect(settings.locator("#inhaal-text")).toContainText("Linked with localhost:8181");
  return settings;
}

test("without a link nothing is kept for Inhaal", async ({ context, serviceWorker }) => {
  const { frame } = await openLecture(context);
  await video.play(frame);
  await video.seek(frame, 65);
  await video.pause(frame);
  await new Promise((resolve) => setTimeout(resolve, 500));
  expect(await queue(serviceWorker)).toEqual([]);
});

test("a kuleuven.be link opens the settings; only a valid address asks to link", async ({ context }) => {
  await context.route("https://www.kuleuven.be/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<title>KU Leuven</title>" }),
  );
  const page = await context.newPage();
  const opened = context.waitForEvent("page");
  await page.goto(
    `https://www.kuleuven.be/#swiftskip-koppel=${encodeURIComponent("https://inhaal.example/")}`,
  );
  const settings = await opened;
  await expect(settings.locator("#inhaal-text")).toContainText("Inhaal at inhaal.example asks to link");
  await expect(page).toHaveURL("https://www.kuleuven.be/");

  await page.goto("https://www.kuleuven.be/other#swiftskip-koppel=http%3A%2F%2Fonveilig.example%2F");
  await expect(page).toHaveURL(/swiftskip-koppel/);
  await page.waitForTimeout(300);
  expect(context.pages()).toHaveLength(3);
});

test("position and watched reach Inhaal; delivered events are forgotten", async ({
  context,
  extensionId,
  serviceWorker,
}) => {
  await link(context, extensionId);
  const { page, frame } = await openLecture(context, { title: "Les 2 (2026-09-24): e2e" });
  const duration = await frame.evaluate(() => document.querySelector("video").duration);
  await video.play(frame);
  await video.seek(frame, 45);
  await video.pause(frame);

  await expect.poll(async () => (await queue(serviceWorker)).length).toBe(1);
  const [event] = await queue(serviceWorker);
  expect(event).toMatchObject({
    type: "recording.progress",
    source: "swiftskip",
    payload: { positionSec: 45 },
  });
  expect(event.payload.durationSec).toBeGreaterThan(45);
  expect(event.payload.recording).toMatchObject({
    title: "Les 2 (2026-09-24): e2e",
    recordedOn: "2026-09-24",
    lectureNumber: 2,
  });
  expect(event.payload.recording.courseCode).toMatch(/^[A-Z0-9]+$/i);
  expect(event.payload.recording.url).toContain("iframe.html");

  await video.play(frame);
  await video.seek(frame, duration * 0.95);
  await video.pause(frame);
  await expect
    .poll(async () => (await queue(serviceWorker)).map((e) => e.type))
    .toEqual(["recording.watched"]);

  const inhaal = await context.newPage();
  await inhaal.goto(ADDRESS);
  await expect.poll(() => inhaal.evaluate(() => window.linked)).toBe(true);
  await expect
    .poll(() => inhaal.evaluate(() => window.received.map((e) => e.type)))
    .toEqual(["recording.watched"]);
  await expect.poll(async () => (await queue(serviceWorker)).length).toBe(0);
  await page.close();
});

test("the player script stays away from the Inhaal page; unlinking stops the bridge", async ({
  context,
  extensionId,
  serviceWorker,
}) => {
  const settings = await link(context, extensionId);
  const registered = () =>
    serviceWorker.evaluate(async () =>
      (await chrome.scripting.getRegisteredContentScripts()).map((script) => script.id),
    );
  await expect.poll(registered).toEqual(["swiftskip-inhaal"]);

  await settings.getByRole("button", { name: "Unlink" }).click();
  await expect(settings.locator("#inhaal-text")).toContainText("Open the settings in Inhaal");
  await expect.poll(registered).toEqual([]);
});

test("without a Toledo lecture title, the recording's own name is passed on", async ({
  context,
  extensionId,
  serviceWorker,
}) => {
  await link(context, extensionId);
  const { frame } = await openLecture(context, { title: "" });
  // On this test page the player shares the Toledo page's origin, so it reads that title.
  const name = "LTI openen";
  await video.play(frame);
  await video.seek(frame, 45);
  await video.pause(frame);
  await expect.poll(async () => (await queue(serviceWorker))[0]?.payload.recording.title).toBe(name);
});

test("a finished download reaches Inhaal with its file name", async ({
  context,
  extensionId,
  serviceWorker,
}) => {
  await link(context, extensionId);
  const { frame } = await openLecture(context, { title: "" });
  await frame.locator("#swiftskip-download").click();
  await expect
    .poll(async () => (await queue(serviceWorker)).find((e) => e.type === "recording.downloaded"), {
      timeout: 30_000,
    })
    .toBeTruthy();
  const event = (await queue(serviceWorker)).find((e) => e.type === "recording.downloaded");
  expect(event.payload.fileName).toMatch(/\.mp4$|\.ts$/);
  expect(event.payload.recording.title).toBe("LTI openen");
});
