import { test, expect, BASE } from "./fixtures.js";

const PAGE = `${BASE}/ultra/courses/_1_1/outline.html`;
const useVerbatim = (serviceWorker, on) =>
  serviceWorker.evaluate((value) => chrome.storage.sync.set({ downloadsToVerbatim: value }), on);
const button = (page, name) => page.locator("[data-row]", { hasText: name }).locator(".velox-slide");

test("no buttons on Toledo while downloads to Verbatim are off", async ({ context, serviceWorker }) => {
  await useVerbatim(serviceWorker, false);
  const page = await context.newPage();
  await page.goto(PAGE);
  await page.waitForTimeout(800);
  await expect(page.locator(".velox-slide")).toHaveCount(0);
});

test("saves a PDF into the course folder and remembers it", async ({ context, serviceWorker }) => {
  await useVerbatim(serviceWorker, true);
  await serviceWorker.evaluate(() => {
    const original = chrome.downloads.download.bind(chrome.downloads);
    globalThis.__requested = [];
    chrome.downloads.download = (options) => {
      globalThis.__requested.push(options);
      return original(options);
    };
  });
  const page = await context.newPage();
  await page.goto(PAGE);

  // PDF rows only: not the Word file, not the folder.
  await expect(page.locator(".velox-slide")).toHaveCount(2);
  await expect(button(page, "Opgave")).toHaveCount(0);
  await expect(button(page, "Lesopnames")).toHaveCount(0);

  await button(page, "Slides Hoofdstuk 1").click();
  await expect(button(page, "Slides Hoofdstuk 1")).toHaveAttribute("data-state", "saved");
  expect(page.url()).toBe(PAGE); // the tap doesn't open the file
  const [request] = await serviceWorker.evaluate(() => globalThis.__requested);
  expect(request.filename).toBe("Verbatim/H00X0A/Slides Hoofdstuk 1.pdf");
  expect(request.conflictAction).toBe("overwrite");

  await page.reload();
  await expect(button(page, "Slides Hoofdstuk 1")).toHaveAttribute("data-state", "saved");
  await expect(button(page, "Verlopen sessie")).toHaveAttribute("data-state", "idle");
});

test("a login page instead of a file is not kept", async ({ context, serviceWorker }) => {
  await useVerbatim(serviceWorker, true);
  await serviceWorker.evaluate(() => {
    const original = chrome.downloads.download.bind(chrome.downloads);
    globalThis.__calls = 0;
    chrome.downloads.download = (options) => {
      globalThis.__calls += 1;
      return original(options);
    };
  });
  const page = await context.newPage();
  await page.goto(PAGE);
  await button(page, "Verlopen sessie").click();
  await expect(button(page, "Verlopen sessie")).toHaveAttribute("data-state", "failed");
  // It was really fetched as text/html, then removed from disk and the list.
  await expect.poll(() => serviceWorker.evaluate(() => globalThis.__calls)).toBe(1);
  const kept = await serviceWorker.evaluate(() => chrome.downloads.search({}));
  expect(kept).toHaveLength(0);
});

test("rows that appear later get a button, and turning it off removes them", async ({
  context,
  serviceWorker,
}) => {
  await useVerbatim(serviceWorker, true);
  const page = await context.newPage();
  await page.goto(PAGE);
  await expect(page.locator(".velox-slide")).toHaveCount(2);
  await page.evaluate(() => {
    document.querySelector("#rows").insertAdjacentHTML(
      "beforeend",
      `<div data-row><a href="/ultra/courses/_1_1/file/_14_1" aria-label="PDF, Later">Later</a>
       <a data-ally-content-id="_14_1" data-ally-file-preview-url="/bbcswebdav/deck.pdf"></a></div>`,
    );
  });
  await expect(page.locator(".velox-slide")).toHaveCount(3);
  await useVerbatim(serviceWorker, false);
  await expect(page.locator(".velox-slide")).toHaveCount(0);
});
