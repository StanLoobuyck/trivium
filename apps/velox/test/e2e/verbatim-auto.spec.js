import { createServer } from "node:http";
import { test, expect, openLecture } from "./fixtures.js";

// A stand-in Verbatim on its port, unless the real one already runs here (the developer's laptop).
async function verbatimOnPort() {
  try {
    const text = await (await fetch("http://127.0.0.1:7861/", { signal: AbortSignal.timeout(1000) })).text();
    if (text.includes("<title>Verbatim</title>")) return null;
    throw new Error("port 7861 is taken by something else");
  } catch (e) {
    if (e.message.includes("taken")) throw e;
  }
  const server = createServer((req, res) => res.end("<!doctype html><title>Verbatim</title>"));
  await new Promise((resolve) => server.listen(7861, "127.0.0.1", resolve));
  return server;
}

test("with Verbatim running, a download goes to Verbatim/<course code>/ by itself", async ({
  context,
  serviceWorker,
}) => {
  const server = await verbatimOnPort();
  try {
    // A user who never touched the setting (the fixture starts from "chose off").
    await serviceWorker.evaluate(() =>
      chrome.storage.sync.set({ downloadsToVerbatim: false, downloadsToVerbatimChosen: false }),
    );
    await serviceWorker.evaluate(() => {
      const original = chrome.downloads.download.bind(chrome.downloads);
      globalThis.__requested = [];
      chrome.downloads.download = (o) => (globalThis.__requested.push(o.filename), original(o));
    });
    const { frame } = await openLecture(context);
    await frame.locator(".ss-dl-main").click();
    await expect(frame.locator("#velox-download")).toHaveAttribute("data-mode", "done", { timeout: 30_000 });
    const names = await serviceWorker.evaluate(() => globalThis.__requested);
    expect(names[names.length - 1]).toMatch(/^Verbatim\/T01E5T\/.+\.mp4$/);
    const after = await serviceWorker.evaluate(() => chrome.storage.sync.get(null));
    expect(after.downloadsToVerbatim).toBe(true);
    expect(after.downloadsToVerbatimChosen).toBeFalsy();
  } finally {
    server?.close();
  }
});
